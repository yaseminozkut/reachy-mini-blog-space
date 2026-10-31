---
title: Reachy Mini Blogs
emoji: 💻
colorFrom: blue
colorTo: green
sdk: static
pinned: false
license: apache-2.0
short_description: Blog posts about Reachy Mini, aggregated weekly
tags:
  - reachy_mini
---

# Reachy Mini Blogs

A static feed of blog posts about **Reachy Mini**, aggregated from:

- The Hugging Face main blog
- Hugging Face community articles
- The Pollen Robotics site

A GitHub Action runs weekly. If the scraped content has changed, it pushes a fresh `index.html` to this Space (and GitHub). If nothing changed, the Space's last-updated timestamp stays the same.

## Local run

```bash
pip install -r requirements.txt
python build.py
open index.html
```
