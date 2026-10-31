---
title: Reachy Mini Blogs
emoji: 💻
colorFrom: gray
colorTo: pink
sdk: static
pinned: false
license: apache-2.0
short_description: Blog posts about Reachy Mini, aggregated weekly
tags:
  - reachy-mini
---

# Reachy Mini Blogs

A static feed of blog posts about **Reachy Mini**, aggregated from:

- The Hugging Face main blog
- Hugging Face community articles
- The Pollen Robotics site

A GitHub Action runs `build.py` on a schedule, regenerates `index.html`, and pushes to both GitHub and this HF Space — but **only when the content actually changes**. The commit history doubles as a changelog of new Reachy Mini posts.

## Local run

```bash
pip install -r requirements.txt
python build.py
open index.html
```
