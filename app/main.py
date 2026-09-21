import os
import time
import html
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable
from urllib.parse import quote

from bs4 import BeautifulSoup
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Supreme Search API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

MAX_LIMIT = 20
CACHE_TTL = int(os.getenv("CACHE_TTL_SECONDS", "300"))
X1337_BASE_URL = os.getenv("X1337_BASE_URL", "https://www.1377x.to").rstrip("/")
TPB_BASE_URL = os.getenv("TPB_BASE_URL", "").strip()


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


def search_piratebay(query: str, limit: int) -> list[SearchResult]:
    """Search through the third-party `thepiratebay-api` Python wrapper.

    A custom TPB_BASE_URL can be supplied through an environment variable.
    """
    try:
        from thepiratebay_api import TorrentClient
    except Exception:
        return []

    kwargs = {"timeout": 25}
    if TPB_BASE_URL:
        kwargs["url"] = TPB_BASE_URL

    found: list[SearchResult] = []
    try:
        with TorrentClient(**kwargs) as client:
            try:
                response = client.search(query, sort_by=TorrentClient.SortBy.SEEDERS_DESC)
            except Exception:
                response = client.search(query)

            torrents = list(getattr(response, "torrents", []) or [])[:limit]
            for item in torrents:
                try:
                    details = client.detail(item.torrent_id)
                    magnet = str(getattr(details, "magnet_link", "") or "")
                    if not magnet.startswith("magnet:"):
                        continue
                    found.append(
                        SearchResult(
                            title=str(getattr(details, "title", None) or getattr(item, "title", "Unknown")),
                            source="PirateBay",
                            size=str(getattr(details, "size", "?") or "?"),
                            seeders=_to_int(getattr(details, "seeders", 0)),
                            leechers=_to_int(getattr(details, "leechers", 0)),
                            magnet=magnet,
                            category=str(getattr(details, "category", "") or ""),
                        )
                    )
                except Exception:
                    continue
    except Exception:
        return []
    return found


def _find_1337x_rows(soup: BeautifulSoup):
    table = soup.find("table", class_=lambda c: c and "table-list" in c)
    if not table:
        return []
    rows = table.find_all("tr")
    return rows[1:] if len(rows) > 1 else []


def search_1337x(query: str, limit: int) -> list[SearchResult]:
    """Search the configured 1337x mirror with Playwright and return magnets."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return []

    user_agent = (
        "Mozilla/5.0 (Linux; Android 11; TV) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/153.0 Safari/537.36"
    )
    results: list[SearchResult] = []
    browser = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            context = browser.new_context(user_agent=user_agent)
            page = context.new_page()
            search_url = f"{X1337_BASE_URL}/search/{quote(query)}/1/"
            page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            soup = BeautifulSoup(page.content(), "html.parser")

            raw_rows = []
            for row in _find_1337x_rows(soup)[:limit]:
                cells = row.find_all("td")
                if len(cells) < 5:
                    continue
                anchors = cells[0].find_all("a", href=True)
                if not anchors:
                    continue
                # The torrent detail link is generally the last useful href in the name cell.
                detail_href = None
                for anchor in reversed(anchors):
                    href = anchor.get("href", "")
                    if href.startswith("/torrent/"):
                        detail_href = href
                        break
                if not detail_href:
                    detail_href = anchors[-1].get("href", "")
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
                    detail_page.goto(detail_url, wait_until="domcontentloaded", timeout=20000)
                    detail_soup = BeautifulSoup(detail_page.content(), "html.parser")
                    magnet_tag = detail_soup.find("a", href=lambda h: h and h.startswith("magnet:"))
                    if not magnet_tag:
                        continue
                    magnet = html.unescape(magnet_tag.get("href", ""))
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
                except Exception:
                    continue
            context.close()
            browser.close()
            browser = None
    except Exception:
        try:
            if browser:
                browser.close()
        except Exception:
            pass
        return []
    return results


def _dedupe(results: Iterable[SearchResult]) -> list[SearchResult]:
    by_key: dict[str, SearchResult] = {}
    for result in results:
        key = result.magnet.split("&")[0].lower().strip() if result.magnet else result.title.lower().strip()
        current = by_key.get(key)
        if not current or result.seeders > current.seeders:
            by_key[key] = result
    return sorted(by_key.values(), key=lambda r: (r.seeders, -r.leechers), reverse=True)


@app.get("/health")
def health():
    return {"ok": True, "service": "Supreme Search API"}


@app.get("/search", response_model=list[SearchResult])
def search(
    q: str = Query(..., min_length=2, max_length=160),
    sources: str = Query("1337x,piratebay"),
    limit: int = Query(12, ge=1, le=MAX_LIMIT),
):
    enabled = {x.strip().lower() for x in sources.split(",") if x.strip()}
    cache_key = f"{q.lower().strip()}|{','.join(sorted(enabled))}|{limit}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    jobs = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        if "1337x" in enabled:
            jobs.append(pool.submit(search_1337x, q, limit))
        if "piratebay" in enabled or "tpb" in enabled:
            jobs.append(pool.submit(search_piratebay, q, limit))

        merged: list[SearchResult] = []
        for future in as_completed(jobs):
            try:
                merged.extend(future.result())
            except Exception:
                pass

    final = _dedupe(merged)[: max(limit, 1) * max(len(jobs), 1)]
    _cache_put(cache_key, final)
    return final
