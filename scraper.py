"""Scrape Reachy Mini blog posts from HF and pollen-robotics.com."""
from __future__ import annotations

import json
import logging
import random
import re
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

HF = "https://huggingface.co"
POLLEN = "https://www.pollen-robotics.com"
UA = {"User-Agent": "reachy-mini-blog-space/1.0 (+https://huggingface.co/spaces)"}
TIMEOUT = 20
KEYWORD = re.compile(r"reachy", re.I)
# Day before Reachy Mini launched (Jul 9 2025) — community scan stops once posts predate this.
REACHY_EPOCH = datetime(2025, 7, 8, tzinfo=timezone.utc)

PRIORITY = {"pollen": 0, "hf-main": 1, "hf-community": 2}


@dataclass
class Post:
    title: str
    url: str
    source: str
    published_at: str = ""
    authors: list[str] = field(default_factory=list)
    thumbnail: str = ""
    description: str = ""
    mirrors: list[tuple[str, str]] = field(default_factory=list)


def _get(url: str, retries: int = 4, patient: bool = False) -> requests.Response | None:
    attempts = 10 if patient else retries
    for attempt in range(attempts):
        try:
            r = requests.get(url, headers=UA, timeout=TIMEOUT)
        except requests.RequestException as e:
            log.debug("GET %s failed: %s", url, e)
            time.sleep(2 + attempt)
            continue
        if r.status_code == 429:
            retry_after = r.headers.get("Retry-After")
            if retry_after:
                try:
                    backoff = float(retry_after)
                except ValueError:
                    backoff = 10.0
            elif patient:
                backoff = 5 + attempt * 4 + random.random()
            else:
                backoff = 2 + attempt * 3 + random.random()
            log.info("429 on %s, sleeping %.1fs (attempt %d/%d)", url, backoff, attempt + 1, attempts)
            time.sleep(backoff)
            continue
        if r.ok:
            return r
        log.debug("GET %s -> %s", url, r.status_code)
        return None
    return None


def _meta(soup: BeautifulSoup, prop: str) -> str:
    el = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
    if not el:
        return ""
    return (el.get("content") or "").strip()


def _norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", t.lower())


def scrape_main_rss() -> list[Post]:
    r = _get(f"{HF}/blog/feed.xml", patient=True)
    if not r:
        return []
    try:
        root = ET.fromstring(r.content)
    except ET.ParseError as e:
        log.warning("RSS parse failed: %s", e)
        return []
    posts = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        if KEYWORD.search(title) or KEYWORD.search(link):
            posts.append(Post(title=title, url=link, source="hf-main", published_at=pub))
    return posts


def _fetch_community_page(p: int, patient: bool = False) -> str | None:
    r = _get(f"{HF}/blog/community?sort=recent&p={p}", patient=patient)
    return r.text if r else None


def _reachy_urls_in(html_text: str) -> list[str]:
    hrefs = set(re.findall(r'href="(/blog/[^"]*reachy[^"]*)"', html_text, re.I))
    out = []
    for h in hrefs:
        parts = h.strip("/").split("/")
        if len(parts) == 3 and parts[0] == "blog":
            out.append(HF + h)
    return out


def _detect_last_page(html_text: str) -> int:
    # HF emits `&amp;p=N` in pagination links, so we allow `;` before `p=` as well as `?` and `&`.
    nums = [int(m) for m in re.findall(r"[?&;]p=(\d+)", html_text)]
    return max(nums) if nums else 0


def _min_post_date_on_page(html_text: str) -> datetime | None:
    dates: list[datetime] = []
    for raw in re.findall(r'<time\b[^>]*datetime="([^"]+)"', html_text):
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
                dates.append(dt)
                break
            except ValueError:
                continue
    return min(dates) if dates else None


def scrape_community(
    max_pages_cap: int = 500,
    max_workers: int = 5,
    cutoff: datetime = REACHY_EPOCH,
    batch_size: int = 15,
) -> list[Post]:
    """Scan /blog/community?p=N newest-first; early-exit once a page's oldest post predates `cutoff`."""
    first = _fetch_community_page(0, patient=True)
    if first is None:
        log.warning("community page 0 fetch failed; skipping community scan")
        return []
    last_page = min(_detect_last_page(first), max_pages_cap)
    log.info("community pagination: last page=%d (cutoff=%s)", last_page, cutoff.date())

    urls: set[str] = set(_reachy_urls_in(first))
    first_min = _min_post_date_on_page(first)
    scanned_pages = 1
    hit_cutoff = first_min is not None and first_min < cutoff

    page = 1
    while page <= last_page and not hit_cutoff:
        batch = list(range(page, min(page + batch_size, last_page + 1)))
        results: dict[int, str] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {ex.submit(_fetch_community_page, p): p for p in batch}
            for fu in as_completed(futures):
                p = futures[fu]
                try:
                    text = fu.result()
                except Exception as e:
                    log.warning("community p=%s failed: %s", p, e)
                    continue
                if text:
                    results[p] = text
                    urls.update(_reachy_urls_in(text))
                scanned_pages += 1

        for p in sorted(results):
            m = _min_post_date_on_page(results[p])
            if m is not None and m < cutoff:
                hit_cutoff = True
                log.info("stopping community scan at p=%d (oldest post on page: %s)", p, m.date())
                break
        page += batch_size

    log.info("community scan: %d pages scanned, %d matching URLs", scanned_pages, len(urls))
    posts = []
    for u in urls:
        slug = u.rsplit("/", 1)[-1].replace("-", " ")
        posts.append(Post(title=slug, url=u, source="hf-community"))
    return posts


def scrape_pollen_site() -> list[Post]:
    r = _get(f"{POLLEN}/reachy-mini/blog/")
    if not r:
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    posts: list[Post] = []
    seen: set[str] = set()
    for a in soup.select('a[href*="/reachy-mini/blog/"]'):
        href = a.get("href", "")
        if not href:
            continue
        full = href if href.startswith("http") else POLLEN + href
        tail = full.rstrip("/").split("/reachy-mini/blog", 1)[-1].strip("/")
        if not tail:
            continue
        if full in seen:
            continue
        seen.add(full)
        title = a.get_text(" ", strip=True)
        if len(title) < 3:
            parent = a.find_parent(["article", "li", "div"])
            if parent:
                h = parent.find(["h1", "h2", "h3"])
                if h:
                    title = h.get_text(" ", strip=True)
        posts.append(Post(title=title or tail, url=full, source="pollen"))
    return posts


def _first_substantive_paragraph(soup: BeautifulSoup) -> str:
    region = soup.select_one("main") or soup.select_one("article") or soup
    for p in region.find_all("p"):
        text = p.get_text(" ", strip=True)
        if len(text) >= 60 and not text.lower().startswith("published"):
            return text
    return ""


def _parse_jsonld(soup: BeautifulSoup) -> dict:
    for tag in soup.find_all("script", type="application/ld+json"):
        raw = tag.string or tag.get_text() or ""
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            for d in data:
                if isinstance(d, dict) and d.get("@type") in {"Article", "SocialMediaPosting", "BlogPosting"}:
                    return d
        elif isinstance(data, dict):
            if data.get("@type") in {"Article", "SocialMediaPosting", "BlogPosting"}:
                return data
    return {}


def _enrich_hf(post: Post) -> Post:
    r = _get(post.url)
    if not r:
        return post
    soup = BeautifulSoup(r.text, "html.parser")

    post.title = _meta(soup, "og:title") or post.title

    ld = _parse_jsonld(soup)
    if ld.get("datePublished"):
        post.published_at = ld["datePublished"]
    img = ld.get("image")
    if isinstance(img, list) and img:
        img = img[0]
    if isinstance(img, dict):
        img = img.get("url") or ""
    if img:
        post.thumbnail = img
    elif not post.thumbnail:
        post.thumbnail = _meta(soup, "og:image")

    authors: list[str] = []
    raw_auths = ld.get("author") or []
    if isinstance(raw_auths, dict):
        raw_auths = [raw_auths]
    for a in raw_auths:
        name = a.get("name") if isinstance(a, dict) else str(a)
        if name and name not in authors:
            authors.append(name)
    if authors:
        post.authors = authors

    post.description = _first_substantive_paragraph(soup) or post.description
    return post


def _enrich_pollen(post: Post) -> Post:
    r = _get(post.url)
    if not r:
        return post
    soup = BeautifulSoup(r.text, "html.parser")
    post.title = _meta(soup, "og:title") or post.title
    post.description = _meta(soup, "og:description") or post.description
    post.thumbnail = _meta(soup, "og:image") or post.thumbnail
    pub = _meta(soup, "article:published_time") or _meta(soup, "date")
    if pub:
        post.published_at = pub

    authors: list[str] = []
    for el in soup.find_all("meta", property="article:author"):
        name = (el.get("content") or "").strip()
        if name and name not in authors:
            authors.append(name)
    if not authors:
        for sel in ['a[rel="author"]', ".byline a", '[itemprop="author"]']:
            for el in soup.select(sel):
                t = el.get_text(" ", strip=True)
                if t and t not in authors:
                    authors.append(t)
    if authors:
        post.authors = authors
    return post


def _enrich(post: Post) -> Post:
    try:
        if post.source == "pollen":
            return _enrich_pollen(post)
        return _enrich_hf(post)
    except Exception as e:
        log.warning("enrich failed for %s: %s", post.url, e)
        return post


def _dedupe(posts: list[Post]) -> list[Post]:
    """Collapse by normalized title; the alternate's URL is attached to the primary as a mirror."""
    by_key: dict[str, Post] = {}
    for p in posts:
        key = _norm_title(p.title)
        if not key:
            continue
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = p
            continue
        if PRIORITY[p.source] < PRIORITY[existing.source]:
            primary, alternate = p, existing
        else:
            primary, alternate = existing, p
        seen = {(src, url) for src, url in primary.mirrors}
        for src, url in alternate.mirrors:
            if (src, url) not in seen and url != primary.url:
                primary.mirrors.append((src, url))
                seen.add((src, url))
        if alternate.url != primary.url and (alternate.source, alternate.url) not in seen:
            primary.mirrors.append((alternate.source, alternate.url))
        by_key[key] = primary
    return list(by_key.values())


_DATE_FORMATS = (
    "%a, %d %b %Y %H:%M:%S %Z",
    "%a, %d %b %Y %H:%M:%S GMT",
    "%Y-%m-%dT%H:%M:%S.%fZ",
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%d",
)


def _parse_date(s: str) -> datetime | None:
    if not s:
        return None
    s = s.strip()
    for fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def date_display(post: Post) -> str:
    dt = _parse_date(post.published_at)
    return dt.strftime("%b %-d, %Y") if dt else ""


def _sort_key(p: Post) -> datetime:
    dt = _parse_date(p.published_at)
    return dt or datetime.min.replace(tzinfo=timezone.utc)


def scrape(community_scan_limit: int = 500) -> list[Post]:
    """HF (rss then community) runs sequentially so we don't slam HF with concurrent requests;
    Pollen runs in parallel in another thread (different host, safe)."""
    log.info("scraping HF and Pollen in parallel")
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_hf = ex.submit(_scrape_hf, community_scan_limit)
        f_pollen = ex.submit(scrape_pollen_site)
        main, community = f_hf.result()
        pollen = f_pollen.result()
    log.info("  main=%d  pollen=%d  community=%d", len(main), len(pollen), len(community))

    all_posts = main + community + pollen
    log.info("enriching %d posts", len(all_posts))
    with ThreadPoolExecutor(max_workers=6) as ex:
        enriched = list(ex.map(_enrich, all_posts))

    deduped = _dedupe(enriched)
    deduped.sort(key=_sort_key, reverse=True)
    log.info("final count after dedupe: %d", len(deduped))
    return deduped


def _scrape_hf(community_scan_limit: int) -> tuple[list[Post], list[Post]]:
    main = scrape_main_rss()
    community = scrape_community(max_pages_cap=community_scan_limit)
    return main, community


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    posts = scrape()
    for p in posts:
        print(f"\n[{p.source}] {p.title}")
        print(f"   url:   {p.url}")
        print(f"   date:  {p.published_at}  ({date_display(p)})")
        print(f"   auth:  {p.authors}")
        print(f"   img:   {p.thumbnail[:80]}")
        print(f"   desc:  {p.description[:140]}")
