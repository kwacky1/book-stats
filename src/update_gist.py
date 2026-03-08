#!/usr/bin/env python3
"""Fetch StoryGraph reading activity and update a GitHub Gist with a 5-line Markdown summary."""

import os
import sys
import re

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

STORYGRAPH_USER = os.environ.get("STORYGRAPH_USERNAME", "")
GIST_ID = os.environ.get("GIST_ID", "")
GITHUB_TOKEN = os.environ.get("GH_TOKEN", "")
GIST_FILENAME = os.environ.get("GIST_FILENAME", "reading-stats.md")

BASE = "https://app.thestorygraph.com"
PROFILE_URL = BASE + "/profile/{user}"
CURRENTLY_READING_URL = BASE + "/currently-reading/{user}"
BOOKS_READ_URL = BASE + "/books-read/{user}"
STATS_URL = BASE + "/stats/{user}"

PAGE_TIMEOUT_MS = 30_000
SETTLE_MS = 5_000


# ---------------------------------------------------------------------------
# Fetching (Playwright — bypasses Cloudflare JS challenge)
# ---------------------------------------------------------------------------

_browser = None
_playwright = None


def _get_browser():
    """Lazily launch a shared headless Chromium instance."""
    global _browser, _playwright
    if _browser is None:
        _playwright = sync_playwright().start()
        _browser = _playwright.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
    return _browser


def close_browser() -> None:
    """Shut down the shared browser if it was started."""
    global _browser, _playwright
    if _browser:
        _browser.close()
        _browser = None
    if _playwright:
        _playwright.stop()
        _playwright = None


def fetch_page(url: str) -> BeautifulSoup:
    """Navigate to *url* in headless Chromium and return a BeautifulSoup tree."""
    browser = _get_browser()
    ctx = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 720},
    )
    page = ctx.new_page()
    page.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
        page.wait_for_timeout(SETTLE_MS)
        html = page.content()
    except PlaywrightTimeout:
        print(f"Timeout loading {url}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"Error fetching {url}: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        ctx.close()

    soup = BeautifulSoup(html, "html.parser")
    page_title = soup.title.string if soup.title else ""
    if "Sign In" in page_title or "sign_in" in page.url:
        print(
            f"StoryGraph redirected to sign-in for {url}. "
            "Ensure the profile is set to Public in StoryGraph settings.",
            file=sys.stderr,
        )
        sys.exit(1)
    return soup


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def clean(text: str) -> str:
    """Collapse whitespace and strip a string."""
    return re.sub(r"\s+", " ", text).strip()


def parse_book_pane(pane) -> dict:
    """Extract title and author from a .book-pane element."""
    info = {"title": "—", "author": "—"}
    ts = pane.select_one(".book-title-author-and-series")
    if not ts:
        return info
    title_link = ts.select_one("a[href*='/books/']")
    if title_link:
        info["title"] = clean(title_link.get_text())
    author_link = ts.select_one("a[href*='/authors/']")
    if author_link:
        info["author"] = clean(author_link.get_text())
    return info


def parse_currently_reading(soup: BeautifulSoup) -> list[dict]:
    """Return a list of currently-reading books [{title, author}, ...]."""
    books = []
    for pane in soup.select(".book-pane"):
        books.append(parse_book_pane(pane))
    return books


def parse_last_finished(soup: BeautifulSoup) -> dict:
    """Return {title, author} for the most recently finished book."""
    pane = soup.select_one(".book-pane")
    if pane:
        return parse_book_pane(pane)
    return {"title": "—", "author": "—"}


def parse_profile_counts(soup: BeautifulSoup) -> dict:
    """Extract 'N Books' and 'N This Year' from the profile header."""
    result = {"total_books": "0", "books_this_year": "0"}
    text = soup.get_text(" ", strip=True)

    total = re.search(r"(\d+)\s+Books?\b", text)
    if total:
        result["total_books"] = total.group(1)

    this_year = re.search(r"(\d+)\s+This\s+Year", text)
    if this_year:
        result["books_this_year"] = this_year.group(1)

    return result


def parse_stats(soup: BeautifulSoup) -> dict:
    """Extract books, pages, and hours from the stats page summary line."""
    result = {"books": "0", "pages": "0", "hours": "0"}
    text = soup.get_text(" ", strip=True)

    # Matches "11 books , 3,085 pages, 13.5 hours" or similar
    books = re.search(r"(\d+)\s*books?\b", text, re.I)
    pages = re.search(r"([\d,]+)\s*pages?\b", text, re.I)
    hours = re.search(r"([\d,.]+)\s*hours?\b", text, re.I)

    if books:
        result["books"] = books.group(1)
    if pages:
        result["pages"] = pages.group(1)
    if hours:
        result["hours"] = hours.group(1)
    return result


# ---------------------------------------------------------------------------
# Markdown builder
# ---------------------------------------------------------------------------

def build_markdown(
    currently_reading: list[dict],
    last_finished: dict,
    books_this_year: str,
    total_books: str,
    pages: str,
) -> str:
    """Return the 5-line Markdown summary."""
    cr = currently_reading[0] if currently_reading else {"title": "—", "author": "—"}
    cr2_line = ""
    if len(currently_reading) > 1:
        cr2 = currently_reading[1]
        cr2_line = f"\U0001F4DA Also reading: *{cr2['title']}* by {cr2['author']}"
    else:
        cr2_line = "\U0001F4DA Also reading: —"

    lines = [
        f"\U0001F4D6 Currently reading: *{cr['title']}* by {cr['author']}",
        cr2_line,
        f"\U0001F3C1 Last finished: *{last_finished['title']}*",
        f"\U0001F4C5 Books this year: {books_this_year}",
        f"\U0001F4CA Total: {total_books} books \u00b7 {pages} pages",
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Gist update
# ---------------------------------------------------------------------------

def update_gist(markdown: str) -> None:
    """Push *markdown* to the configured GitHub Gist."""
    if not GIST_ID or not GITHUB_TOKEN:
        print("GIST_ID or GH_TOKEN not set — skipping Gist update.", file=sys.stderr)
        return

    url = f"https://api.github.com/gists/{GIST_ID}"
    payload = {"files": {GIST_FILENAME: {"content": markdown}}}
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }

    try:
        resp = requests.patch(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        print(f"Gist updated: https://gist.github.com/{GIST_ID}")
    except requests.RequestException as exc:
        print(f"Failed to update Gist: {exc}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if not STORYGRAPH_USER:
        print("Set STORYGRAPH_USERNAME environment variable.", file=sys.stderr)
        sys.exit(1)

    user = STORYGRAPH_USER

    try:
        profile_soup = fetch_page(PROFILE_URL.format(user=user))
        cr_soup = fetch_page(CURRENTLY_READING_URL.format(user=user))
        read_soup = fetch_page(BOOKS_READ_URL.format(user=user))
        stats_soup = fetch_page(STATS_URL.format(user=user))
    finally:
        close_browser()

    currently_reading = parse_currently_reading(cr_soup)
    last_finished = parse_last_finished(read_soup)
    counts = parse_profile_counts(profile_soup)
    stats = parse_stats(stats_soup)

    markdown = build_markdown(
        currently_reading=currently_reading,
        last_finished=last_finished,
        books_this_year=counts["books_this_year"],
        total_books=counts["total_books"],
        pages=stats["pages"],
    )

    print(markdown)
    update_gist(markdown)


if __name__ == "__main__":
    main()


if __name__ == "__main__":
    main()
