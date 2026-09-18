#!/usr/bin/env python3
"""Rewrite the LIVE block in the profile README from aggregate GitHub activity only."""
import json, os, urllib.error, urllib.parse, urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

USER = "VontariusF"
ROOT = Path(__file__).resolve().parents[1]
TOKEN = os.environ.get("LIVE_STATS_TOKEN") or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
BLOCKS = " ▁▂▃▄▅▆▇█"

def request(url):
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "vontarius-live-stats",
        "X-GitHub-Api-Version": "2022-11-28",
        **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}),
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw.decode())
    except urllib.error.HTTPError as err:
        try:
            err.read()
        except Exception:
            pass
        return err.code, None

def get(url):
    status, data = request(url)
    if status != 200 or data is None:
        raise RuntimeError(f"github {status}")
    return data

def search_commits(q, per_page=100):
    url = "https://api.github.com/search/commits?" + urllib.parse.urlencode({
        "q": q, "sort": "committer-date", "order": "desc", "per_page": per_page,
    })
    data = get(url)
    return data.get("items") or [], data.get("total_count") or 0

def list_repos():
    repos = []
    for page in range(1, 6):
        url = "https://api.github.com/user/repos?" + urllib.parse.urlencode({
            "per_page": 100, "page": page, "affiliation": "owner", "sort": "pushed",
        })
        status, data = request(url)
        if status != 200 or not isinstance(data, list):
            return []
        repos.extend(data)
        if len(data) < 100:
            break
    return repos

def can_read_private_commits(repos):
    for repo in repos:
        if not repo.get("private"):
            continue
        status, _ = request(f"https://api.github.com/repos/{repo['full_name']}/commits?per_page=1")
        if status == 200:
            return True
        if status == 403:
            return False
    return False

def collect_day_counts(repos, since_dt):
    """Return only per-day commit counts. Never keep messages, SHAs, or repo names."""
    since = since_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    by_day = Counter()
    for repo in repos:
        pushed = repo.get("pushed_at") or ""
        if pushed and pushed < since:
            continue
        name = repo["full_name"]
        url = f"https://api.github.com/repos/{name}/commits?" + urllib.parse.urlencode({
            "author": USER, "since": since, "per_page": 100,
        })
        status, data = request(url)
        if status != 200 or not isinstance(data, list):
            continue
        for item in data:
            day = (((item.get("commit") or {}).get("committer") or {}).get("date") or "")[:10]
            if day:
                by_day[day] += 1
    return by_day

now = datetime.now(timezone.utc)
user = get(f"https://api.github.com/users/{USER}")
since14 = (now - timedelta(days=13)).replace(hour=0, minute=0, second=0, microsecond=0)
repos = list_repos() if TOKEN else []
private_ok = can_read_private_commits(repos) if repos else False

if private_ok:
    by_day = collect_day_counts(repos, since14)
    today_key = now.date().isoformat()
    week_key = (now - timedelta(days=6)).date().isoformat()
    today_n = sum(n for d, n in by_day.items() if d >= today_key)
    week_n = sum(n for d, n in by_day.items() if d >= week_key)
    total14 = sum(by_day.values())
    scope = "public + private"
else:
    items, total14 = search_commits(f"author:{USER} committer-date:>={since14.date().isoformat()}")
    _, today_n = search_commits(f"author:{USER} committer-date:>={now.date().isoformat()}", per_page=1)
    _, week_n = search_commits(
        f"author:{USER} committer-date:>={(now - timedelta(days=6)).date().isoformat()}",
        per_page=1,
    )
    by_day = Counter()
    for item in items:
        raw = (((item.get("commit") or {}).get("committer") or {}).get("date") or "")[:10]
        if raw:
            by_day[raw] += 1
    scope = "public commits"

days = [(now - timedelta(days=13 - i)).date().isoformat() for i in range(14)]
peak = max([by_day[d] for d in days] or [1]) or 1
spark = "".join(BLOCKS[min(8, round(8 * by_day[d] / peak))] if by_day[d] else "·" for d in days)

stamp = now.strftime("%Y-%m-%d %H:%M UTC")
pub = user.get("public_repos", 0)
followers = user.get("followers", 0)
md = f"""### right now

`{stamp}` · {scope} · refreshes about hourly

| today | this week | last 14 days | public repos | followers |
|------:|----------:|-------------:|-------------:|----------:|
| **{today_n}** | **{week_n}** | **{total14}** | **{pub}** | **{followers}** |

`{days[0][5:]}` {spark} `{days[-1][5:]}`
"""

readme_path = ROOT / "README.md"
readme = readme_path.read_text()
start, end = "<!-- LIVE:START -->", "<!-- LIVE:END -->"
if start not in readme or end not in readme:
    raise SystemExit("README missing LIVE markers")
pre, rest = readme.split(start, 1)
_, post = rest.split(end, 1)
readme_path.write_text(pre + start + "\n" + md + "\n" + end + post)
print("ok", stamp, scope, "today", today_n, "week", week_n, "14d", total14)
