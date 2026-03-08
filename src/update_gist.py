#!/usr/bin/env python3
"""Fetch StoryGraph reading activity and update a GitHub Gist with a 5-line Markdown summary."""

import os
import sys
import json
import re

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

STORYGRAPH_USER = os.environ.get("STORYGRAPH_USERNAME", "")
GIST_ID = os.environ.get("GIST_ID", "")
GITHUB_TOKEN = os.environ.get("GH_TOKEN", "")
GIST_FILENAME = os.environ.get("GIST_FILENAME", "reading-stats.md")

PROFILE_URL = "https://app.thestorygraph.com/profile/{user}"
STATS_URL = "https://app.thestorygraph.com/stats/{user}"
GOALS_URL = "https://app.thestorygraph.com/reading_goals/{user}"

HEADERS = {
    "User-Agent": "book-stats/1.0 (https://github.com)",
    "Accept": "text/html",
}


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def fetch_page(url: str) -> BeautifulSoup:
    """Return a BeautifulSoup tree for *url*, or exit on failure."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"Error fetching {url}: {exc}", file=sys.stderr)
        sys.exit(1)
    return BeautifulSoup(resp.text, "html.parser")


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def clean(text: str) -> str:
    """Collapse whitespace and strip a string."""
    return re.sub(r"\s+", " ", text).strip()


def parse_currently_reading(soup: BeautifulSoup) -> tuple[str, str, str]:
    """Extract (title, author, progress) from the currently-reading section.

    Returns placeholder strings when the section is missing.
    """
    section = (
        soup.select_one(".currently-reading")
        or soup.select_one("[data-controller='currently-reading']")
        or soup.find(id=re.compile(r"currently.reading", re.I))
    )
    if not section:
        return ("—", "—", "0%")

    # Title: first .book-title-author-and-series or first <a> with /books/
    title_el = (
        section.select_one(".book-title-author-and-series h3")
        or section.select_one(".book-title")
        or section.select_one("a[href*='/books/']")
    )
    title = clean(title_el.get_text()) if title_el else "—"

    # Author
    author_el = (
        section.select_one(".book-title-author-and-series p")
        or section.select_one(".authors-info")
        or section.select_one(".author-name")
    )
    author = clean(author_el.get_text()).removeprefix("by ") if author_el else "—"

    # Progress: look for a percentage string like "42%"
    progress = "0%"
    progress_el = section.select_one(".progress") or section.select_one("[style*=width]")
    if progress_el:
        pct_match = re.search(r"(\d+)\s*%", progress_el.get_text() + str(progress_el.get("style", "")))
        if pct_match:
            progress = f"{pct_match.group(1)}%"
    else:
        pct_match = re.search(r"(\d+)\s*%", section.get_text())
        if pct_match:
            progress = f"{pct_match.group(1)}%"

    return (title, author, progress)


def parse_last_finished(soup: BeautifulSoup) -> tuple[str, str]:
    """Extract (title, date) of the most recently finished book.

    Falls back gracefully when the section is not present.
    """
    section = (
        soup.select_one(".books-pane-list")
        or soup.select_one(".read-books")
        or soup.find("div", class_=re.compile(r"book.pane", re.I))
    )
    if not section:
        return ("—", "—")

    book = section.select_one(".book-pane") or section.select_one("[class*='book-pane']")
    if not book:
        return ("—", "—")

    title_el = (
        book.select_one(".book-title-author-and-series h3")
        or book.select_one(".book-title")
        or book.select_one("a[href*='/books/']")
    )
    title = clean(title_el.get_text()) if title_el else "—"

    date_el = book.select_one(".date-read") or book.select_one("span[class*='date']")
    date_str = clean(date_el.get_text()) if date_el else "—"

    return (title, date_str)


def parse_yearly_stats(soup: BeautifulSoup) -> tuple[str, str]:
    """Extract (books_read, pages_read) from the stats page."""
    section = (
        soup.select_one(".stats-section")
        or soup.select_one("[class*='stats']")
        or soup.find("div", class_=re.compile(r"stat", re.I))
    )
    text = section.get_text(" ", strip=True) if section else soup.get_text(" ", strip=True)

    books_match = re.search(r"(\d+)\s*books?\s*read", text, re.I)
    pages_match = re.search(r"([\d,]+)\s*pages?\s*read", text, re.I)

    books = books_match.group(1) if books_match else "0"
    pages = pages_match.group(1) if pages_match else "0"
    return (books, pages)


def parse_goal(soup: BeautifulSoup) -> tuple[str, str, str]:
    """Extract (current, target, percentage) for the yearly reading goal."""
    section = (
        soup.select_one(".reading-goal")
        or soup.select_one("[class*='goal']")
        or soup.find("div", class_=re.compile(r"goal", re.I))
    )
    text = section.get_text(" ", strip=True) if section else soup.get_text(" ", strip=True)

    # Patterns like "8 / 30", "8 of 30", "8/30"
    goal_match = re.search(r"(\d+)\s*[/of]+\s*(\d+)", text, re.I)
    if goal_match:
        current, target = goal_match.group(1), goal_match.group(2)
        pct = round(int(current) / int(target) * 100) if int(target) else 0
        return (current, target, f"{pct}%")

    return ("0", "0", "0%")


# ---------------------------------------------------------------------------
# Markdown builder
# ---------------------------------------------------------------------------

def build_markdown(
    title: str,
    progress: str,
    last_title: str,
    last_date: str,
    books_read: str,
    goal_current: str,
    goal_target: str,
    goal_pct: str,
) -> str:
    """Return the 5-line Markdown summary."""
    lines = [
        f"\U0001F4D6 Currently reading: *{title}*",
        f"\u23F3 Progress: {progress}",
        f"\U0001F3C1 Last finished: *{last_title}* ({last_date})",
        f"\U0001F4C5 Books this year: {books_read}",
        f"\U0001F3AF Goal: {goal_current} / {goal_target} ({goal_pct})",
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

    profile_soup = fetch_page(PROFILE_URL.format(user=STORYGRAPH_USER))
    stats_soup = fetch_page(STATS_URL.format(user=STORYGRAPH_USER))
    goals_soup = fetch_page(GOALS_URL.format(user=STORYGRAPH_USER))

    title, _author, progress = parse_currently_reading(profile_soup)
    last_title, last_date = parse_last_finished(profile_soup)
    books_read, _pages_read = parse_yearly_stats(stats_soup)
    goal_current, goal_target, goal_pct = parse_goal(goals_soup)

    markdown = build_markdown(
        title=title,
        progress=progress,
        last_title=last_title,
        last_date=last_date,
        books_read=books_read,
        goal_current=goal_current,
        goal_target=goal_target,
        goal_pct=goal_pct,
    )

    print(markdown)
    update_gist(markdown)


if __name__ == "__main__":
    main()
