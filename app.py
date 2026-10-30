"""Gradio Space: a curated feed of Reachy Mini blog posts."""
from __future__ import annotations

import dataclasses
import html
import json
import logging
import os
import pathlib
import threading
import time
from datetime import datetime, timezone

import gradio as gr

from scraper import Post, date_display, scrape

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("app")

REFRESH_INTERVAL_S = int(os.environ.get("REFRESH_INTERVAL_S", 3600))
COMMUNITY_SCAN_LIMIT = int(os.environ.get("COMMUNITY_SCAN_LIMIT", 500))

# Cached posts persisted to disk between scrapes so visitors never see an empty page after a
# container sleep/wake cycle. Gitignored by default — commit it if you want the same guarantee
# across a fresh deploy.
SNAPSHOT_PATH = pathlib.Path(os.environ.get("SNAPSHOT_PATH", "cache_snapshot.json"))

_lock = threading.Lock()
_cache: dict[str, object] = {"posts": [], "updated_at": None}


SOURCE_LABEL = {
    "hf-main": "HF Main Blog",
    "hf-community": "HF Community Blog",
    "pollen": "Pollen Robotics Website",
}


def _refresh_cache() -> None:
    log.info("starting scrape")
    try:
        posts = scrape(community_scan_limit=COMMUNITY_SCAN_LIMIT)
    except Exception as e:
        log.exception("scrape failed: %s", e)
        return
    now = datetime.now(timezone.utc)
    with _lock:
        _cache["posts"] = posts
        _cache["updated_at"] = now
    log.info("cache updated with %d posts", len(posts))
    _save_snapshot(posts, now)


def _save_snapshot(posts: list[Post], updated_at: datetime) -> None:
    try:
        payload = {
            "updated_at": updated_at.isoformat(),
            "posts": [dataclasses.asdict(p) for p in posts],
        }
        tmp = SNAPSHOT_PATH.with_suffix(SNAPSHOT_PATH.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(SNAPSHOT_PATH)
        log.info("snapshot saved to %s (%d posts)", SNAPSHOT_PATH, len(posts))
    except OSError as e:
        log.warning("snapshot save failed: %s", e)


def _load_snapshot() -> None:
    if not SNAPSHOT_PATH.exists():
        log.info("no snapshot at %s; cache starts empty", SNAPSHOT_PATH)
        return
    try:
        payload = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        raw_posts = payload.get("posts", [])
        posts: list[Post] = []
        for d in raw_posts:
            # JSON turns tuples into lists; coerce `mirrors` back to list[tuple[str, str]].
            mirrors = [tuple(m) for m in d.get("mirrors", []) if len(m) == 2]
            d = {**d, "mirrors": mirrors}
            posts.append(Post(**d))
        updated_at = datetime.fromisoformat(payload["updated_at"])
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as e:
        log.warning("snapshot load failed: %s", e)
        return
    with _lock:
        _cache["posts"] = posts
        _cache["updated_at"] = updated_at
    log.info("snapshot loaded: %d posts, updated_at=%s", len(posts), updated_at.isoformat())


def _initial_scrape() -> None:
    _refresh_cache()


def _background_refresher() -> None:
    while True:
        time.sleep(REFRESH_INTERVAL_S)
        _refresh_cache()


def _escape(s: str) -> str:
    return html.escape(s or "", quote=True)


def _card_html(post: Post) -> str:
    thumb = _escape(post.thumbnail)
    thumb_block = (
        f'<div class="rm-thumb" style="background-image:url(\'{thumb}\')"></div>'
        if post.thumbnail
        else '<div class="rm-thumb rm-thumb--empty"></div>'
    )
    date = _escape(date_display(post))
    authors = _escape(", ".join(post.authors)) if post.authors else ""
    source = _escape(SOURCE_LABEL.get(post.source, post.source))
    desc = _escape((post.description or "").strip())
    if len(desc) > 220:
        desc = desc[:217].rstrip() + "…"

    mirrors_block = ""
    if post.mirrors:
        links = " · ".join(
            f'<a href="{_escape(url)}" target="_blank" rel="noopener noreferrer">'
            f'{_escape(SOURCE_LABEL.get(src, src))} ↗</a>'
            for src, url in post.mirrors
        )
        mirrors_block = f'<div class="rm-mirrors">Also on: {links}</div>'

    return f"""
<article class="rm-card">
  <a class="rm-card-link" href="{_escape(post.url)}" target="_blank" rel="noopener noreferrer">
    {thumb_block}
    <div class="rm-card-body">
      <div class="rm-card-meta">
        <span class="rm-badge rm-badge--{_escape(post.source)}">{source}</span>
        {f'<span class="rm-date">{date}</span>' if date else ''}
      </div>
      <h3 class="rm-title">{_escape(post.title)}</h3>
      {f'<p class="rm-authors">{authors}</p>' if authors else ''}
      {f'<p class="rm-desc">{desc}</p>' if desc else ''}
    </div>
  </a>
  {mirrors_block}
</article>"""


def _grid_html(posts: list[Post]) -> str:
    if not posts:
        return '<div class="rm-empty">Loading the first scrape — this can take a few minutes.</div>'
    cards = "\n".join(_card_html(p) for p in posts)
    return f'<section class="rm-grid">{cards}</section>'


def _updated_label() -> str:
    with _lock:
        updated = _cache["updated_at"]
        count = len(_cache["posts"])  # type: ignore[arg-type]
    if updated is None:
        return "Loading…"
    local = updated.astimezone()
    return f"{count} posts · last updated {local.strftime('%b %-d, %Y %H:%M %Z')}"


def _render() -> tuple[str, str]:
    with _lock:
        posts = list(_cache["posts"])  # type: ignore[arg-type]
    return _grid_html(posts), _updated_label()


CSS = """
.rm-wrap { max-width: 1120px; margin: 0 auto; padding: 8px 4px 32px; }
.rm-header { padding: 8px 4px 20px; }
.rm-header h1 {
  font-size: 32px; font-weight: 800; margin: 0 0 6px;
  background: linear-gradient(90deg, #ec4899, #6366f1);
  -webkit-background-clip: text; background-clip: text; color: transparent;
  letter-spacing: -0.02em;
}
.rm-header p { color: var(--body-text-color-subdued); margin: 0; font-size: 15px; }
.rm-toolbar {
  display: flex; align-items: center; justify-content: space-between;
  gap: 12px; padding: 4px; margin-bottom: 10px;
  color: var(--body-text-color-subdued); font-size: 13px;
}
.rm-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 18px;
}
.rm-empty {
  padding: 48px 16px; text-align: center;
  color: var(--body-text-color-subdued); font-size: 15px;
}
.rm-card {
  background: var(--background-fill-primary);
  border: 1px solid var(--border-color-primary);
  border-radius: 14px; overflow: hidden;
  transition: transform 160ms ease, box-shadow 160ms ease, border-color 160ms ease;
  display: flex; flex-direction: column;
}
.rm-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 10px 24px -14px rgba(0,0,0,0.25);
  border-color: #ec4899;
}
.rm-card-link { color: inherit; text-decoration: none; display: block; }
.rm-thumb {
  width: 100%; aspect-ratio: 16/9;
  background-size: cover; background-position: center;
  background-color: var(--background-fill-secondary);
}
.rm-thumb--empty {
  background: linear-gradient(135deg, #fdf2f8, #eef2ff);
}
.rm-card-body { padding: 14px 16px 16px; }
.rm-card-meta {
  display: flex; align-items: center; gap: 10px;
  margin-bottom: 8px; font-size: 12px;
}
.rm-badge {
  padding: 2px 8px; border-radius: 999px;
  font-size: 11px; font-weight: 600;
  background: #fce7f3; color: #9d174d;
}
.rm-badge--hf-community { background: #ede9fe; color: #5b21b6; }
.rm-badge--pollen { background: #e0f2fe; color: #075985; }
.rm-date { color: var(--body-text-color-subdued); }
.rm-title {
  margin: 0 0 6px;
  font-size: 16px; font-weight: 700; line-height: 1.35;
  color: var(--body-text-color);
}
.rm-authors {
  margin: 0 0 10px;
  font-size: 12.5px; color: var(--body-text-color-subdued);
}
.rm-desc {
  margin: 0;
  font-size: 13.5px; line-height: 1.5;
  color: var(--body-text-color-subdued);
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical;
  overflow: hidden;
}
.rm-mirrors {
  padding: 10px 16px 14px;
  margin-top: auto;
  border-top: 1px dashed var(--border-color-primary);
  font-size: 12px;
  color: var(--body-text-color-subdued);
}
.rm-mirrors a {
  color: var(--body-text-color-subdued);
  text-decoration: none;
  border-bottom: 1px solid transparent;
  transition: color 120ms ease, border-color 120ms ease;
}
.rm-mirrors a:hover { color: #ec4899; border-bottom-color: #ec4899; }
"""


def build_app() -> gr.Blocks:
    with gr.Blocks(css=CSS, title="Reachy Mini Blog", theme=gr.themes.Soft()) as demo:
        with gr.Column(elem_classes="rm-wrap"):
            gr.HTML(
                """
                <div class="rm-header">
                  <h1>Reachy Mini Blog</h1>
                  <p>Blog posts about <strong>Reachy Mini</strong>, from the Hugging Face main and community blog, and Pollen Robotics website. Refreshed hourly.</p>
                </div>
                """
            )
            updated = gr.Markdown("Loading…", elem_classes="rm-toolbar")
            grid = gr.HTML('<div class="rm-empty">Starting first scrape…</div>')

            demo.load(_render, outputs=[grid, updated], show_progress="hidden")

    return demo


def main() -> None:
    _load_snapshot()
    threading.Thread(target=_initial_scrape, daemon=True).start()
    threading.Thread(target=_background_refresher, daemon=True).start()
    build_app().queue().launch(server_name="0.0.0.0")


if __name__ == "__main__":
    main()
