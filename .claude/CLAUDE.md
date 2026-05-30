# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the CLI

```bash
source venv/bin/activate
python manga_scrape.py
```

The script is an interactive REPL: search for a manga title → select from results → browse chapters → download a chapter.

## Dependencies

All dependencies are managed in a local `venv/`. No `requirements.txt` exists yet — current key packages: `beautifulsoup4`, `lxml`, `requests`, `playwright`, `typer`.

To install a new package: `venv/bin/pip install <package>` and then freeze to `requirements.txt` if one is created.

## Architecture

Everything lives in a single file: `manga_scrape.py`. All scraping targets `weebcentral.com`.

**Data flow:**

1. `get_manga_list(search_query)` — POSTs to the simple search endpoint, parses the result HTML, returns a list of dicts with `title`, `series_uuid`, `series_url`, `img_url`.
2. `get_manga_series(series_uuid)` — GETs the `/series/{uuid}/full-chapter-list` page, returns a list of `{chapter_link, chapter_title}` dicts in reverse-chronological order.
3. `download_chapter(chapter_link)` — Fetches the chapter page, finds the HTMX lazy-load section (`<section hx-get="...">`) that holds image URLs, then fires a second GET to that endpoint with `?reading_style=long_strip` and the `HX-Request: true` header. Pages are saved as zero-padded files (`001.png`, `002.png`, …) inside `downloads/{safe_folder_name}/`.

**Key detail:** The site uses HTMX for lazy image loading. The real image list is not in the initial HTML — it requires a second request mimicking an HTMX fetch (see `download_chapter` lines 122–148).

`safe_filename()` strips the " | Weeb Central" suffix from page titles and replaces special characters before using the result as the download folder name.

Downloaded chapters land in `downloads/` (git-ignored). Cover images from search results can be saved to `search_covers/` via `download_covers()`, though this is not wired into the interactive flow.
