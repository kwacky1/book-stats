# 📚 book-stats

A lightweight script that scrapes your public [StoryGraph](https://app.thestorygraph.com) profile and pushes a **5-line Markdown summary** of your reading activity to a GitHub Gist.

## Output example

```
📖 Currently reading: *The Left Hand of Darkness*
⏳ Progress: 42%
🏁 Last finished: *Piranesi* (15 Feb 2026)
📅 Books this year: 8
🎯 Goal: 8 / 30 (27%)
```

## Requirements

- Python 3.10+
- A public StoryGraph profile
- A GitHub Gist (create one manually first)
- A GitHub personal access token with `gist` scope

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/<you>/book-stats.git
cd book-stats
pip install -r requirements.txt
```

### 2. Create a GitHub Gist

Go to <https://gist.github.com> and create a new Gist with any filename (e.g. `reading-stats.md`). Copy the **Gist ID** from the URL.

### 3. Create a GitHub personal access token

Go to *Settings → Developer settings → Personal access tokens → Tokens (classic)* and create a token with the **gist** scope.

### 4. Set environment variables

| Variable              | Description                                  |
|-----------------------|----------------------------------------------|
| `STORYGRAPH_USERNAME` | Your StoryGraph username (public profile)    |
| `GIST_ID`             | The ID of the Gist to update                 |
| `GH_TOKEN`            | GitHub personal access token with gist scope |
| `GIST_FILENAME`       | *(optional)* Filename inside the Gist — defaults to `reading-stats.md` |

### 5. Run locally

```bash
export STORYGRAPH_USERNAME="your-username"
export GIST_ID="abc123..."
export GH_TOKEN="ghp_..."
python src/update_gist.py
```

On Windows (PowerShell):

```powershell
$env:STORYGRAPH_USERNAME = "your-username"
$env:GIST_ID = "abc123..."
$env:GH_TOKEN = "ghp_..."
python src\update_gist.py
```

## GitHub Actions (automatic daily updates)

The included workflow runs once per day at 06:00 UTC.

1. Go to your repository **Settings → Secrets and variables → Actions**.
2. Add the three required secrets: `STORYGRAPH_USERNAME`, `GIST_ID`, `GH_TOKEN`.
3. The workflow also supports **manual dispatch** from the Actions tab.

## How it works

1. Fetches your public StoryGraph profile, stats, and goals pages.
2. Parses the HTML with BeautifulSoup using predictable CSS selectors (`.currently-reading`, `.book-pane`, `.stats-section`, etc.).
3. Builds a 5-line Markdown snippet.
4. PATCHes the Gist via the GitHub API.

## Resilience

- Each parser function falls back through multiple CSS selectors and regex patterns.
- Missing sections produce placeholder dashes (`—`) rather than crashing.
- If StoryGraph changes their markup, update the selectors in `src/update_gist.py`.

## Licence

MIT
