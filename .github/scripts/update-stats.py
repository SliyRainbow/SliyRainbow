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


def colors(config, dark):
    return ({"bg": "#11151e", "ink": "#eef0fa", "muted": "#a1abbd", "line": "#293142", "soft": "#202737", "accent": config["accent"]}
            if dark else {"bg": "#fafaff", "ink": "#202638", "muted": "#646f83", "line": "#e1e5ef", "soft": "#e9edf4", "accent": config["lightAccent"]})


def text(x, y, value, fill, size=16, weight=400, extra=""):
    return f'<text x="{x}" y="{y}" fill="{fill}" font-size="{size}" font-weight="{weight}" {extra}>{escape(str(value))}</text>'


def document(w, h, title, body, c):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-labelledby="title"><title id="title">{escape(title)}</title><style>text{{font-family:'Segoe UI','Microsoft YaHei',Arial,sans-serif}}.mono{{font-family:Consolas,'Courier New',monospace}}</style><rect x=".5" y=".5" width="{w-1}" height="{h-1}" rx="14" fill="{c['bg']}" stroke="{c['line']}"/>{body}</svg>\n'''


def overview(data, config, dark, mobile):
    c = colors(config, dark)
    w, h = (600, 328) if mobile else (1000, 178)
    body = text(29, 35, "GITHUB / OVERVIEW", c["accent"], 14 if mobile else 12, 600, 'letter-spacing="1.4"')
    body += text(w-29, 35, data["updated"] + " UTC", c["muted"], 12 if mobile else 11, extra='text-anchor="end" class="mono"')
    metrics = [("Public repos", data["public_repos"]), ("Stars earned", data["stars"]), ("Followers", data["followers"]), ("Contributions / 365d", data["contributions"])]
    for index, (label, value) in enumerate(metrics):
        x = 29 + (index % 2) * 285 if mobile else 29 + index * 245
        y = 105 + (index // 2) * 137 if mobile else 106
        body += text(x, y, f"{value:,}", c["ink"], 45 if mobile else 43, 650)
        body += text(x, y+32, label, c["muted"], 17 if mobile else 14)
        if not mobile and index:
            body += f'<line x1="{x-24}" y1="67" x2="{x-24}" y2="145" stroke="{c["line"]}"/>'
    return document(w, h, f'{data["username"]}: '+', '.join(f'{v} {k}' for k,v in metrics), body, c)


def activity(data, config, dark, mobile):
    c = colors(config, dark)
    w, h = (600, 410) if mobile else (1000, 252)
    today = date.fromisoformat(data["updated"])
    first = today - timedelta(days=89 if mobile else 364)
    values = {day: count for day, count in data["calendar"].items() if day >= first.isoformat()}
    active = sum(count > 0 for count in values.values())
    body = text(29, 35, "CONTRIBUTION ACTIVITY", c["accent"], 14 if mobile else 12, 600, 'letter-spacing="1.4"')
    body += text(w-29, 35, "90 DAYS" if mobile else "365 DAYS", c["muted"], 13 if mobile else 11, extra='text-anchor="end" class="mono"')
    sunday = first - timedelta(days=(first.weekday()+1) % 7)
    columns = (today-sunday).days // 7 + 1
    step = 36 if mobile else 17
    cell = 28 if mobile else 12
    left, top = ((w - columns*step + step-cell)/2, 94) if mobile else (66, 83)
    max_count = max(values.values(), default=0)
    for i in range(columns * 7):
        day = sunday + timedelta(days=i)
        if day < first or day > today:
            continue
        count = values[day.isoformat()]
        x = left + (i // 7) * step
        y = top + (i % 7) * step
        opacity = 0 if count == 0 else .3 + .7 * count / max_count
        body += f'<rect x="{x:.1f}" y="{y}" width="{cell}" height="{cell}" rx="{5 if mobile else 2.5}" fill="{c["soft"]}"/>'
        if count:
            body += f'<rect x="{x:.1f}" y="{y}" width="{cell}" height="{cell}" rx="{5 if mobile else 2.5}" fill="{c["accent"]}" opacity="{opacity:.3f}"><title>{day.isoformat()}: {count} contributions</title></rect>'
    if not mobile:
        for day_index, label in [(1,"Mon"),(3,"Wed"),(5,"Fri")]:
            body += text(27, top+day_index*step+10, label, c["muted"], 10)
        last_month = None
        for column in range(columns):
            day = sunday + timedelta(days=column*7+3)
            if day.month != last_month:
                if column < columns-1:
                    body += text(left+column*step, 67, day.strftime("%b"), c["muted"], 10)
                last_month = day.month
    else:
        body += text(left, 73, first.strftime("%b %d"), c["muted"], 14)
        body += text(w-left, 73, today.strftime("%b %d"), c["muted"], 14, extra='text-anchor="end"')
    bottom = 380 if mobile else 225
    body += text(29, bottom, f'{sum(values.values()):,} contributions  ·  {active} active days', c["muted"], 17 if mobile else 13)
    body += text(w-29, bottom, "Less ··· More", c["accent"], 14 if mobile else 11, extra='text-anchor="end"')
    return document(w, h, f'{data["username"]}: {sum(values.values())} contributions in {len(values)} days; {active} active days', body, c)


LANGUAGE_COLORS = {"C#":"#aa83ef", "Go":"#62cde2", "TypeScript":"#77aaf2", "JavaScript":"#edcf77", "HTML":"#f08c84", "CSS":"#b9a1f5", "Python":"#6bafde", "C++":"#ee89b2", "C":"#9da6b7", "Vue":"#6dccb1", "Shell":"#9dd47c", "PowerShell":"#829dee"}


def languages(data, config, dark, mobile):
    c = colors(config, dark)
    entry_count = min(6, len(data["languages"]))
    rows = (entry_count + 1) // 2
    w, h = (600, max(185, 172 + max(0, rows-1)*64)) if mobile else (1000, 178)
    body = text(29, 35, "CODE / LANGUAGES", c["accent"], 14 if mobile else 12, 600, 'letter-spacing="1.4"')
    body += text(w-29, 35, "PUBLIC ORIGINAL REPOS", c["muted"], 11, extra='text-anchor="end" class="mono"')
    total = sum(entry["bytes"] for entry in data["languages"])
    entries = [dict(entry) for entry in data["languages"][:5]]
    if len(data["languages"]) > 5:
        entries.append({"name":"Other", "bytes":sum(entry["bytes"] for entry in data["languages"][5:])})
    if not total:
        body += text(29, 105, "No public code language data yet.", c["muted"], 20)
    else:
        x, bar_y = 29, 69
        body += f'<defs><clipPath id="bar"><rect x="29" y="{bar_y}" width="{w-58}" height="12" rx="6"/></clipPath></defs><g clip-path="url(#bar)">'
        for index, entry in enumerate(entries):
            color = LANGUAGE_COLORS.get(entry["name"], [config["accent"], config["secondary"], "#aeb7ca"][index % 3])
            span = entry["bytes"] / total * (w-58)
            body += f'<rect x="{x:.3f}" y="{bar_y}" width="{span+.1:.3f}" height="12" fill="{color}"/>'
            x += span
        body += '</g>'
        for index, entry in enumerate(entries):
            color = LANGUAGE_COLORS.get(entry["name"], [config["accent"], config["secondary"], "#aeb7ca"][index % 3])
            x = 29 + (index % (2 if mobile else 3)) * (285 if mobile else 320)
            y = 131 + (index // (2 if mobile else 3)) * (64 if mobile else 33)
            percent = entry["bytes"] / total * 100
            value = "<0.1" if percent < .05 else f"{percent:.1f}"
            body += f'<circle cx="{x+4}" cy="{y-5}" r="4" fill="{color}"/>'
            body += text(x+18, y, entry["name"], c["ink"], 18 if mobile else 14, 500)
            body += text(x+(250 if mobile else 275), y, value+"%", c["muted"], 16 if mobile else 13, extra='text-anchor="end" class="mono"')
    return document(w, h, data["username"]+': public code languages; excludes forks, private code and profile artwork', body, c)


def render(root, config, data):
    output = root / "assets"
    output.mkdir(parents=True, exist_ok=True)
    files = {}
    for dark in (False, True):
        for mobile in (False, True):
            suffix = ("-mobile" if mobile else "") + ("-dark" if dark else "") + ".svg"
            for name, renderer in [("stats", overview), ("activity", activity), ("languages", languages)]:
                files[name+suffix] = renderer(data, config, dark, mobile)
    files["public-stats.json"] = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    for name, content in files.items():
        destination = output / name
        temporary = output / (name + ".tmp")
        temporary.write_text(content, encoding="utf-8", newline="\n")
        temporary.replace(destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.root.resolve()
    config = json.loads((root / ".github/profile.json").read_text(encoding="utf-8"))
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
