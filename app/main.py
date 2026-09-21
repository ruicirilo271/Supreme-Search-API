import html
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable
from urllib.parse import parse_qs, quote, urlparse

from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

APP_VERSION = "1.1.0"
MAX_LIMIT = 20
MAX_PER_SOURCE = max(1, min(12, int(os.getenv("MAX_PER_SOURCE", "8"))))
CACHE_TTL = max(30, int(os.getenv("CACHE_TTL_SECONDS", "300")))
X1337_BASE_URL = os.getenv("X1337_BASE_URL", "https://www.1377x.to").rstrip("/")
TPB_BASE_URL = os.getenv("TPB_BASE_URL", "").strip().rstrip("/")

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger("supreme-search")

app = FastAPI(
    title="Supreme Search API",
    version=APP_VERSION,
    description="Backend de pesquisa para a aplicação Supreme Search TV.",
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
            # Algumas versões do wrapper poderão já expor detalhes no resultado.
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
    """Pesquisa através do wrapper Python `thepiratebay-api`."""
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

    # Se não foi definida uma base URL, tenta um mirror indicado pelo próprio wrapper.
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


def _find_1337x_rows(soup: BeautifulSoup):
    table = soup.find("table", class_=lambda c: c and "table-list" in c)
    if not table:
        return []
    rows = table.find_all("tr")
    return rows[1:] if len(rows) > 1 else []


def _block_heavy_resources(route):
    try:
        resource_type = route.request.resource_type
        if resource_type in {"image", "media", "font"}:
            route.abort()
        else:
            route.continue_()
    except Exception:
        try:
            route.continue_()
        except Exception:
            pass


def search_1337x(query: str, limit: int) -> list[SearchResult]:
    """Pesquisa o mirror 1337x configurado usando Chromium/Playwright."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        logger.warning("Playwright unavailable: %s", exc)
        return []

    user_agent = (
        "Mozilla/5.0 (Linux; Android 11; TV) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/153.0 Safari/537.36"
    )
    results: list[SearchResult] = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
            )
            try:
                context = browser.new_context(user_agent=user_agent)
                context.route("**/*", _block_heavy_resources)
                page = context.new_page()
                search_url = f"{X1337_BASE_URL}/search/{quote(query, safe='')}/1/"
                page.goto(search_url, wait_until="domcontentloaded", timeout=25000)
                soup = BeautifulSoup(page.content(), "html.parser")

                raw_rows = []
                for row in _find_1337x_rows(soup)[:limit]:
                    cells = row.find_all("td")
                    if len(cells) < 5:
                        continue
                    anchors = cells[0].find_all("a", href=True)
                    if not anchors:
                        continue

                    detail_href = ""
                    for anchor in reversed(anchors):
                        href = anchor.get("href", "")
                        if href.startswith("/torrent/"):
                            detail_href = href
                            break
                    if not detail_href:
                        detail_href = anchors[-1].get("href", "")
                    if not detail_href:
                        continue

                    raw_rows.append(
                        {
                            "title": cells[0].get_text(" ", strip=True),
                            "seeders": _to_int(cells[1].get_text(strip=True)),
                            "leechers": _to_int(cells[2].get_text(strip=True)),
                            "date": cells[3].get_text(" ", strip=True),
                            "size": cells[4].get_text(" ", strip=True),
                            "detail": detail_href,
                        }
                    )

                detail_page = context.new_page()
                for row in raw_rows:
                    try:
                        detail_url = row["detail"]
                        if detail_url.startswith("/"):
                            detail_url = X1337_BASE_URL + detail_url
                        detail_page.goto(detail_url, wait_until="domcontentloaded", timeout=15000)
                        detail_soup = BeautifulSoup(detail_page.content(), "html.parser")
                        magnet_tag = detail_soup.find("a", href=lambda h: h and h.startswith("magnet:"))
                        if not magnet_tag:
                            continue
                        magnet = html.unescape(magnet_tag.get("href", ""))
                        if not magnet.startswith("magnet:"):
                            continue

                        category = ""
                        category_link = detail_soup.find("a", href=lambda h: h and "/cat/" in h)
                        if category_link:
                            category = category_link.get_text(" ", strip=True)

                        results.append(
                            SearchResult(
                                title=row["title"],
                                source="1337x",
                                size=row["size"],
                                seeders=row["seeders"],
                                leechers=row["leechers"],
                                magnet=magnet,
                                date=row["date"],
                                category=category,
                            )
                        )
                    except Exception as exc:
                        logger.debug("1337x detail failed: %s", exc)
                context.close()
            finally:
                browser.close()
    except Exception as exc:
        logger.warning("1337x search failed: %s", exc)
        return []

    return results


@app.get("/")
def root():
    return {
        "ok": True,
        "service": "Supreme Search API",
        "version": APP_VERSION,
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
    }


@app.get("/sources")
def sources():
    return {
        "sources": [
            {"id": "1337x", "name": "1337x", "enabled": True},
            {"id": "piratebay", "name": "PirateBay", "enabled": True},
        ]
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
