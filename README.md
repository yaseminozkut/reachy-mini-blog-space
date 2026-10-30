---
title: Reachy Mini Blog
emoji: 🤖
colorFrom: pink
colorTo: indigo
sdk: gradio
sdk_version: 5.0.0
app_file: app.py
pinned: false
license: apache-2.0
short_description: Blog posts about Reachy Mini from Hugging Face and Pollen Robotics
tags:
  - reachy-mini
---

# Reachy Mini Blog

A curated feed of blog posts about **Reachy Mini**, gathered from:

- The Hugging Face main blog (`huggingface.co/blog`)
- Hugging Face community articles (`huggingface.co/blog/<org>/<slug>`)
- The Pollen Robotics site (`pollen-robotics.com/reachy-mini/blog/`)

Posts are scraped at Space boot and refreshed in the background every hour.
Visitors always see the cached list — no waiting on page load.

## Local run

```bash
pip install -r requirements.txt
python app.py
```
