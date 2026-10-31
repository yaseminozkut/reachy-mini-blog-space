"""Generate index.html from the current scraped data."""
from __future__ import annotations

import html as html_lib
import logging
from datetime import datetime, timezone
from pathlib import Path

from scraper import Post, date_display, scrape

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("build")

OUT_PATH = Path("index.html")

SOURCE_LABEL = {
    "hf-main": "HF Main Blog",
    "hf-community": "HF Community Blog",
    "pollen": "Pollen Robotics Website",
}


def _escape(s: str) -> str:
    return html_lib.escape(s or "", quote=True)


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
            f"{_escape(SOURCE_LABEL.get(src, src))} ↗</a>"
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


CSS = """
:root {
  --bg: #ffffff;
  --bg-soft: #f8fafc;
  --fg: #1f2937;
  --fg-muted: #6b7280;
  --border: #e5e7eb;
  --pink: #ec4899;
  --indigo: #6366f1;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0b0f19;
    --bg-soft: #1f2937;
    --fg: #f3f4f6;
    --fg-muted: #9ca3af;
    --border: #374151;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
  background: var(--bg);
  color: var(--fg);
  line-height: 1.5;
}
.rm-wrap { max-width: 1120px; margin: 0 auto; padding: 32px 20px 48px; }
.rm-header { padding: 8px 4px 20px; }
.rm-header h1 {
  font-size: 36px; font-weight: 800; margin: 0 0 8px;
  background: linear-gradient(90deg, var(--pink), var(--indigo));
  -webkit-background-clip: text; background-clip: text; color: transparent;
  letter-spacing: -0.02em;
}
.rm-header p { color: var(--fg-muted); margin: 0; font-size: 15px; }
.rm-toolbar {
  padding: 4px; margin-bottom: 16px;
  color: var(--fg-muted); font-size: 13px;
}
.rm-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 18px;
}
.rm-empty {
  padding: 48px 16px; text-align: center;
  color: var(--fg-muted); font-size: 15px;
}
.rm-card {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 14px; overflow: hidden;
  transition: transform 160ms ease, box-shadow 160ms ease, border-color 160ms ease;
  display: flex; flex-direction: column;
}
.rm-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 10px 24px -14px rgba(0,0,0,0.25);
  border-color: var(--pink);
}
.rm-card-link { color: inherit; text-decoration: none; display: block; }
.rm-thumb {
  width: 100%; aspect-ratio: 16/9;
  background-size: cover; background-position: center;
  background-color: var(--border);
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
.rm-date { color: var(--fg-muted); }
.rm-title {
  margin: 0 0 6px;
  font-size: 16px; font-weight: 700; line-height: 1.35;
  color: var(--fg);
}
.rm-authors {
  margin: 0 0 10px;
  font-size: 12.5px; color: var(--fg-muted);
}
.rm-desc {
  margin: 0;
  font-size: 13.5px; line-height: 1.5;
  color: var(--fg-muted);
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical;
  overflow: hidden;
}
.rm-mirrors {
  padding: 10px 16px 14px;
  margin-top: auto;
  border-top: 1px dashed var(--border);
  font-size: 12px;
  color: var(--fg-muted);
}
.rm-mirrors a {
  color: var(--fg-muted);
  text-decoration: none;
  border-bottom: 1px solid transparent;
  transition: color 120ms ease, border-color 120ms ease;
}
.rm-mirrors a:hover { color: var(--pink); border-bottom-color: var(--pink); }
.rm-footer {
  margin-top: 48px; padding-top: 20px; border-top: 1px solid var(--border);
  color: var(--fg-muted); font-size: 12.5px; text-align: center;
}
.rm-footer a { color: var(--fg-muted); }
"""

HEADER_HTML = """
<div class="rm-header">
  <h1>Reachy Mini Blogs</h1>
  <p>Blog posts about <strong>Reachy Mini</strong>, from the Hugging Face blog, the HF community, and Pollen Robotics.</p>
</div>
"""


def render(posts: list[Post], updated_at: datetime) -> str:
    cards = "\n".join(_card_html(p) for p in posts)
    grid = (
        f'<section class="rm-grid">{cards}</section>'
        if posts
        else '<div class="rm-empty">No posts yet.</div>'
    )
    toolbar = f'<div class="rm-toolbar">{len(posts)} posts · last updated {updated_at.strftime("%b %-d, %Y %H:%M UTC")}</div>'
    footer = (
        '<div class="rm-footer">'
        'Source: <a href="https://github.com/yaseminozkut/reachy-mini-blog-space" '
        'target="_blank" rel="noopener">github.com/yaseminozkut/reachy-mini-blog-space</a>'
        "</div>"
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Reachy Mini Blogs</title>
<meta name="description" content="Blog posts about Reachy Mini, aggregated from Hugging Face and Pollen Robotics">
<style>{CSS}</style>
</head>
<body>
<div class="rm-wrap">
{HEADER_HTML}
{toolbar}
{grid}
{footer}
</div>
</body>
</html>
"""


def main() -> None:
    log.info("scraping")
    posts = scrape()
    now = datetime.now(timezone.utc)
    html = render(posts, now)
    OUT_PATH.write_text(html, encoding="utf-8")
    log.info("wrote %s (%d posts, %d bytes)", OUT_PATH, len(posts), len(html))


if __name__ == "__main__":
    main()
