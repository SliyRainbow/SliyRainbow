"""Generate profile SVGs using only public GitHub endpoints; no dependencies."""

import argparse
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from html import escape
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.request


class CalendarParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.cells = {}
        self.counts = {}
        self.tooltip = None
        self.text = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "td" and attrs.get("data-date"):
            self.cells[attrs["id"]] = attrs["data-date"]
        if tag == "tool-tip" and attrs.get("for", "").startswith("contribution-day-"):
            self.tooltip = attrs["for"]
            self.text = []

    def handle_data(self, data):
        if self.tooltip:
            self.text.append(data)

    def handle_endtag(self, tag):
        if tag == "tool-tip" and self.tooltip:
            text = "".join(self.text).strip()
            match = re.match(r"([\d,]+) contributions?\b", text)
            if match:
                self.counts[self.tooltip] = int(match[1].replace(",", ""))
            elif text.startswith("No contributions"):
                self.counts[self.tooltip] = 0
            else:
                raise ValueError("Unrecognized public contribution count; preserving existing cards.")
            self.tooltip = None


def get(url, token=None, as_json=True):
    headers = {"User-Agent": "GitHub-Profile-Public-Statistics", "Accept-Language": "en-US"}
    if url.startswith("https://api.github.com/"):
        headers["Accept"] = "application/vnd.github+json"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
        if token:
            headers["Authorization"] = "Bearer " + token
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=35) as response:
                text = response.read().decode("utf-8")
                return json.loads(text) if as_json else text
        except urllib.error.HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise RuntimeError(f"Public GitHub request failed (HTTP {error.code}).") from None
        except urllib.error.URLError:
            if attempt == 2:
                raise RuntimeError("Public GitHub request failed; existing cards are preserved.") from None
        time.sleep(2 ** attempt)


def collect(username, token, today):
    user = get(f"https://api.github.com/users/{username}", token)
    repos = []
    for page in range(1, 101):
        batch = get(f"https://api.github.com/users/{username}/repos?type=owner&per_page=100&page={page}", token)
        repos.extend(repo for repo in batch if not repo["private"] and repo["owner"]["login"].casefold() == username.casefold())
        if len(batch) < 100:
            break
    else:
        raise RuntimeError("Repository pagination exceeded the supported limit.")
    original = [repo for repo in repos if not repo["fork"]]
    language_bytes = defaultdict(int)
    for repo in original:
        if repo["name"].casefold() == username.casefold():
            continue
        for language, size in get(repo["languages_url"], token).items():
            language_bytes[language] += size
    first = today - timedelta(days=364)
    parser = CalendarParser()
    # The default profile calendar rolls across years. Explicit from/to parameters
    # can switch GitHub to a single calendar year, so filter the rolling view here.
    parser.feed(get(f"https://github.com/users/{username}/contributions", as_json=False))
    calendar = {}
    for cell_id, day in parser.cells.items():
        if first.isoformat() <= day <= today.isoformat():
            if cell_id not in parser.counts:
                raise RuntimeError("Contribution calendar is incomplete; existing cards are preserved.")
            calendar[day] = parser.counts[cell_id]
    expected = {(first + timedelta(days=i)).isoformat() for i in range(365)}
    if set(calendar) != expected:
        raise RuntimeError(f"Expected 365 calendar days, received {len(calendar)}; existing cards are preserved.")
    languages = sorted(language_bytes.items(), key=lambda entry: (-entry[1], entry[0]))
    return {
        "username": username,
        "updated": today.isoformat(),
        "source": "Public GitHub REST API and public profile contribution calendar",
        "scope": "Languages exclude forks, private repositories and the profile repository. Calendar includes only publicly visible counts.",
        "public_repos": user["public_repos"],
        "stars": sum(repo["stargazers_count"] for repo in original),
        "followers": user["followers"],
        "contributions": sum(calendar.values()),
        "calendar": dict(sorted(calendar.items())),
        "languages": [{"name": name, "bytes": size} for name, size in languages],
    }


from render_community import render


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--username", help="Render another public account for an unpublished preview.")
    args = parser.parse_args()
    root = args.root.resolve()
    config = json.loads((root / ".github/profile.json").read_text(encoding="utf-8"))
    if args.username:
        config["username"] = args.username
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", config["username"]):
        raise RuntimeError("Invalid GitHub username.")
    data = collect(config["username"], os.environ.get("GITHUB_TOKEN"), datetime.now(timezone.utc).date())
    render(root, config, data)
    print(json.dumps({"account": data["username"], "date": data["updated"], "public_repos": data["public_repos"], "stars": data["stars"], "followers": data["followers"], "contributions_365d": data["contributions"], "languages": len(data["languages"])}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
