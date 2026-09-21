import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable
from urllib.parse import parse_qs, urlparse

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

APP_VERSION = "2.3.0"
MAX_LIMIT = 50
MAX_PER_SOURCE = max(1, min(50, int(os.getenv("MAX_PER_SOURCE", "50"))))
CACHE_TTL = max(30, int(os.getenv("CACHE_TTL_SECONDS", "300")))
TPB_BASE_URL = os.getenv("TPB_BASE_URL", "").strip().rstrip("/")

# 1337x changed generic search behaviour. The maintained py1337x wrapper
# recommends category searches because generic .search() can return empty.
_raw_1337x_urls = os.getenv(
    "X1337_BASE_URLS",
    "https://www.1337x.to,https://1337x.to,https://1337x.st,https://x1337x.ws,https://x1337x.eu,https://x1337x.cc",
)
X1337_BASE_URLS = [x.strip().rstrip("/") for x in _raw_1337x_urls.split(",") if x.strip()]
if os.getenv("X1337_BASE_URL"):
    preferred = os.getenv("X1337_BASE_URL", "").strip().rstrip("/")
    if preferred:
        X1337_BASE_URLS = [preferred] + [x for x in X1337_BASE_URLS if x != preferred]

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger("supreme-search")

app = FastAPI(
    title="Supreme Search API",
    version=APP_VERSION,
    description="Backend de pesquisa para Supreme Search 4K.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


class SearchResult(BaseModel):
    title: str
    source: str
    size: str = "?"
    seeders: int = 0
    leechers: int = 0
    magnet: str
    date: str = ""
    category: str = ""


_cache: dict[str, tuple[float, list[SearchResult]]] = {}
_cache_lock = threading.Lock()


def _to_int(value) -> int:
    try:
        return int(str(value).replace(",", "").strip())
    except Exception:
        return 0


def _clean_query(value: str) -> str:
    return " ".join((value or "").split()).strip()


def _cache_get(key: str):
    with _cache_lock:
        item = _cache.get(key)
        if not item:
            return None
        created, results = item
        if time.time() - created > CACHE_TTL:
            _cache.pop(key, None)
            return None
        return results


def _cache_put(key: str, results: list[SearchResult]):
    with _cache_lock:
        _cache[key] = (time.time(), results)


def _magnet_key(magnet: str, title: str) -> str:
    try:
        parsed = urlparse(magnet)
        xt = parse_qs(parsed.query).get("xt", [])
        if xt:
            return xt[0].lower().strip()
    except Exception:
        pass
    return (magnet or title).lower().strip()


def _dedupe(results: Iterable[SearchResult]) -> list[SearchResult]:
    by_key: dict[str, SearchResult] = {}
    for result in results:
        key = _magnet_key(result.magnet, result.title)
        current = by_key.get(key)
        if not current or result.seeders > current.seeders:
            by_key[key] = result
    return sorted(
        by_key.values(),
        key=lambda r: (r.seeders, -r.leechers, r.title.lower()),
        reverse=True,
    )


def _tpb_collect(client, query: str, limit: int) -> list[SearchResult]:
    from thepiratebay_api import TorrentClient

    try:
        response = client.search(query, sort_by=TorrentClient.SortBy.SEEDERS_DESC)
    except Exception:
        response = client.search(query)

    found: list[SearchResult] = []
    torrents = list(getattr(response, "torrents", []) or [])[:limit]
    for item in torrents:
        try:
            magnet = str(getattr(item, "magnet_link", "") or "")
            details = item
            if not magnet.startswith("magnet:"):
                details = client.detail(item.torrent_id)
                magnet = str(getattr(details, "magnet_link", "") or "")
            if not magnet.startswith("magnet:"):
                continue
            found.append(
                SearchResult(
                    title=str(getattr(details, "title", None) or getattr(item, "title", "Unknown")),
                    source="PirateBay",
                    size=str(getattr(details, "size", None) or getattr(item, "size", "?") or "?"),
                    seeders=_to_int(getattr(details, "seeders", None) or getattr(item, "seeders", 0)),
                    leechers=_to_int(getattr(details, "leechers", None) or getattr(item, "leechers", 0)),
                    magnet=magnet,
                    category=str(getattr(details, "category", "") or ""),
                )
            )
        except Exception as exc:
            logger.debug("TPB detail failed: %s", exc)
    return found


def search_piratebay(query: str, limit: int) -> list[SearchResult]:
    try:
        from thepiratebay_api import TorrentClient
    except Exception as exc:
        logger.warning("thepiratebay-api unavailable: %s", exc)
        return []

    kwargs = {"timeout": 20}
    if TPB_BASE_URL:
        kwargs["url"] = TPB_BASE_URL

    try:
        with TorrentClient(**kwargs) as client:
            return _tpb_collect(client, query, limit)
    except Exception as first_error:
        logger.warning("PirateBay primary search failed: %s", first_error)

    if not TPB_BASE_URL:
        try:
            with TorrentClient(timeout=15) as probe:
                mirrors = probe.mirrors()
                alive = list(getattr(mirrors, "alive", []) or [])
            if alive:
                mirror_url = str(getattr(alive[0], "url", "") or "").rstrip("/")
                if mirror_url:
                    with TorrentClient(url=mirror_url, timeout=20) as client:
                        return _tpb_collect(client, query, limit)
        except Exception as mirror_error:
            logger.warning("PirateBay mirror fallback failed: %s", mirror_error)
    return []


def _1337x_categories():
    from py1337x import category
    return [
        category.TV,
        category.MOVIES,
        category.ANIME,
        category.DOCUMENTARIES,
        category.APPS,
        category.GAMES,
        category.MUSIC,
        category.OTHER,
    ]


def _1337x_candidates(client, query: str, limit: int):
    candidates = {}
    target = max(limit, 12)

    for cat in _1337x_categories():
        try:
            response = client.search(query, page=1, category=cat, sort_by="seeders", order="desc")
            items = list(getattr(response, "items", []) or [])
            logger.info("1337x category %s returned %d listing(s)", cat, len(items))
            for item in items:
                tid = str(getattr(item, "torrent_id", "") or "")
                if not tid:
                    continue
                current = candidates.get(tid)
                if current is None or _to_int(getattr(item, "seeders", 0)) > _to_int(getattr(current, "seeders", 0)):
                    candidates[tid] = item
            if len(candidates) >= target:
                break
        except Exception as exc:
            logger.debug("1337x category %s failed: %s", cat, exc)

    return sorted(
        candidates.values(),
        key=lambda item: _to_int(getattr(item, "seeders", 0)),
        reverse=True,
    )[:target]


def _1337x_detail(base_url: str, item):
    from py1337x import Py1337x

    torrent_id = str(getattr(item, "torrent_id", "") or "")
    if not torrent_id:
        return None

    client = Py1337x(base_url=base_url, requests_kwargs={"timeout": 15})
    info = client.info(torrent_id=torrent_id)
    magnet = str(getattr(info, "magnet_link", "") or "")
    if not magnet.startswith("magnet:"):
        return None

    return SearchResult(
        title=str(getattr(info, "name", None) or getattr(item, "name", "Unknown")),
        source="1337x",
        size=str(getattr(info, "size", None) or getattr(item, "size", "?") or "?"),
        seeders=_to_int(getattr(info, "seeders", None) or getattr(item, "seeders", 0)),
        leechers=_to_int(getattr(info, "leechers", None) or getattr(item, "leechers", 0)),
        magnet=magnet,
        date=str(getattr(info, "date_uploaded", None) or getattr(item, "time", "") or ""),
        category=str(getattr(info, "category", "") or ""),
    )


def search_1337x(query: str, limit: int) -> list[SearchResult]:
    """Category-aware 1337x search with multiple-domain fallback."""
    try:
        from py1337x import Py1337x
    except Exception as exc:
        logger.warning("py1337x unavailable: %s", exc)
        return []

    for base_url in X1337_BASE_URLS:
        try:
            logger.info("1337x trying %s", base_url)
            client = Py1337x(base_url=base_url, requests_kwargs={"timeout": 15})
            candidates = _1337x_candidates(client, query, limit)
            if not candidates:
                logger.warning("1337x %s returned no category listings", base_url)
                continue

            results: list[SearchResult] = []
            with ThreadPoolExecutor(max_workers=min(8, len(candidates))) as pool:
                futures = [pool.submit(_1337x_detail, base_url, item) for item in candidates]
                for future in as_completed(futures):
                    try:
                        result = future.result()
                        if result:
                            results.append(result)
                            if len(results) >= limit:
                                break
                    except Exception as exc:
                        logger.debug("1337x detail failed on %s: %s", base_url, exc)

            if results:
                results.sort(key=lambda r: r.seeders, reverse=True)
                logger.info("1337x %s returned %d magnet result(s)", base_url, len(results))
                return results[:limit]

            logger.warning("1337x %s listings found but no magnets resolved", base_url)
        except Exception as exc:
            logger.warning("1337x %s failed: %s", base_url, exc)

    logger.warning("1337x exhausted all configured domains for %r", query)
    return []


STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def root():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"), media_type="text/html")


@app.get("/api")
def api_info():
    return {
        "ok": True,
        "service": "Supreme Search API",
        "version": APP_VERSION,
        "web": "/",
        "health": "/health",
        "search": "/search?q=ubuntu&sources=1337x,piratebay&limit=8",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "Supreme Search API",
        "version": APP_VERSION,
        "sources": ["1337x", "piratebay"],
        "search_1337x": "py1337x category search + domain fallback",
    }


@app.get("/sources")
def sources():
    return {
        "sources": [
            {
                "id": "1337x",
                "name": "1337x",
                "enabled": True,
                "strategy": "category-search",
                "domains": X1337_BASE_URLS,
            },
            {"id": "piratebay", "name": "PirateBay", "enabled": True},
        ]
    }


@app.get("/diagnostics/1337x")
def diagnostics_1337x(q: str = Query("ubuntu", min_length=2, max_length=80)):
    started = time.time()
    results = search_1337x(_clean_query(q), 3)
    return {
        "ok": bool(results),
        "query": q,
        "count": len(results),
        "seconds": round(time.time() - started, 2),
        "domains": X1337_BASE_URLS,
        "results": results,
    }


@app.get("/search", response_model=list[SearchResult])
def search(
    q: str = Query(..., min_length=2, max_length=160),
    sources: str = Query("1337x,piratebay"),
    limit: int = Query(10, ge=1, le=MAX_LIMIT),
):
    query = _clean_query(q)
    if len(query) < 2:
        raise HTTPException(status_code=400, detail="Pesquisa demasiado curta")

    requested = {x.strip().lower() for x in sources.split(",") if x.strip()}
    aliases = {"tpb": "piratebay", "pirate-bay": "piratebay"}
    enabled = {aliases.get(x, x) for x in requested} & {"1337x", "piratebay"}
    if not enabled:
        raise HTTPException(status_code=400, detail="Nenhuma fonte válida. Usa 1337x e/ou piratebay.")

    cache_key = f"{query.lower()}|{','.join(sorted(enabled))}|{limit}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    per_source_limit = min(limit, MAX_PER_SOURCE)
    jobs = {}
    merged: list[SearchResult] = []

    with ThreadPoolExecutor(max_workers=len(enabled)) as pool:
        if "1337x" in enabled:
            jobs[pool.submit(search_1337x, query, per_source_limit)] = "1337x"
        if "piratebay" in enabled:
            jobs[pool.submit(search_piratebay, query, per_source_limit)] = "piratebay"

        for future in as_completed(jobs):
            source_name = jobs[future]
            try:
                results = future.result()
                logger.info("%s returned %d results for %r", source_name, len(results), query)
                merged.extend(results)
            except Exception as exc:
                logger.warning("%s search crashed: %s", source_name, exc)

    final = _dedupe(merged)[:limit]
    _cache_put(cache_key, final)
    return final
