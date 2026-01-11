#!/usr/bin/env python3
"""
Convert conference paper CSV to Markdown table with GitHub repo info.

Usage:
    python3 csv_to_md.py ICCV25/iccv2025_papers.csv
    # Output: ICCV25/readme.md
"""

import csv
import sys
import re
import json
import time
import os
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple, Dict

# GitHub token from environment variable (optional, increases rate limit from 60 to 5000/hour)
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')


def parse_github_url(url: str) -> Optional[Tuple[str, str]]:
    """Parse GitHub URL and return (owner, repo) or None."""
    if not url:
        return None
    # Match: https://github.com/owner/repo[/...]
    match = re.match(r'https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?(?:/.*)?$', url)
    if match:
        return (match.group(1), match.group(2))
    return None


def load_cache(cache_path: Path) -> dict:
    """Load GitHub info cache from JSON file."""
    if cache_path.exists():
        try:
            with open(cache_path, encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def save_cache(cache_path: Path, cache: dict) -> None:
    """Save GitHub info cache to JSON file."""
    with open(cache_path, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def get_github_info(owner: str, repo: str) -> Optional[Dict]:
    """
    Fetch repo info from GitHub API.
    Returns dict with: about, language, stars, forks, watches
    Returns None on error, "RATE_LIMIT" on rate limit exceeded.
    """
    url = f'https://api.github.com/repos/{owner}/{repo}'
    headers = {
        'User-Agent': 'PANDA-DATASETS-Scraper/1.0',
        'Accept': 'application/vnd.github.v3+json',
    }
    if GITHUB_TOKEN:
        headers['Authorization'] = f'token {GITHUB_TOKEN}'

    req = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return {
                'about': data.get('description', '') or '',
                'language': data.get('language', '') or '',
                'stars': data.get('stargazers_count', 0),
                'forks': data.get('forks_count', 0),
                'watches': data.get('subscribers_count', 0),
                'fetched_at': datetime.now().isoformat(),
            }
    except urllib.error.HTTPError as e:
        if e.code == 403:
            # Rate limit exceeded
            reset_time = e.headers.get('X-RateLimit-Reset')
            if reset_time:
                reset_dt = datetime.fromtimestamp(int(reset_time))
                wait_secs = (reset_dt - datetime.now()).total_seconds()
                print(f"Rate limit exceeded. Resets at {reset_dt} ({int(wait_secs)}s)")
            return "RATE_LIMIT"  # Signal to stop fetching
        elif e.code == 404:
            print(f"  Repo not found: {owner}/{repo}")
            return None
        else:
            print(f"  HTTP error {e.code} for {owner}/{repo}")
            return None
    except Exception as e:
        print(f"  Error fetching {owner}/{repo}: {e}")
        return None


def csv_to_md(csv_path: Path) -> None:
    """Convert CSV to Markdown with GitHub info."""
    conf_dir = csv_path.parent
    out_path = conf_dir / "readme.md"
    cache_path = conf_dir / "github_cache.json"

    # Load existing cache
    cache = load_cache(cache_path)
    cache_hits = 0
    api_calls = 0

    # Read CSV
    rows = []
    with open(csv_path, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            code_url = row.get('code_url', '').strip()
            # Only include papers with code_url
            if code_url:
                rows.append(row)

    print(f"Found {len(rows)} papers with code URLs")
    if GITHUB_TOKEN:
        print("Using GitHub token (rate limit: 5000/hour)")
    else:
        print("No GitHub token (rate limit: 60/hour). Set GITHUB_TOKEN env var to increase.")

    # Fetch GitHub info for each paper
    github_info = {}
    rate_limited = False
    for i, row in enumerate(rows):
        code_url = row.get('code_url', '').strip()
        parsed = parse_github_url(code_url)

        if parsed:
            owner, repo = parsed
            cache_key = f"{owner}/{repo}"

            if cache_key in cache:
                github_info[code_url] = cache[cache_key]
                cache_hits += 1
            elif not rate_limited:
                print(f"[{i+1}/{len(rows)}] Fetching {cache_key}...")
                info = get_github_info(owner, repo)
                if info == "RATE_LIMIT":
                    rate_limited = True
                    print("Stopping API calls due to rate limit. Will use cached data.")
                elif info:
                    cache[cache_key] = info
                    github_info[code_url] = info
                    api_calls += 1
                    # Save cache periodically
                    if api_calls % 10 == 0:
                        save_cache(cache_path, cache)
                    # Rate limiting: 2 second delay
                    time.sleep(2)

    # Save final cache
    save_cache(cache_path, cache)
    print(f"Cache hits: {cache_hits}, API calls: {api_calls}")

    # Write markdown
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('| title | code | about | language | stars | forks | watches | paper | pass^4 |\n')
        f.write('|-------|------|-------|----------|-------|-------|---------|-------|--------|\n')

        for row in rows:
            title = row.get('title', '').replace('|', '\\|')
            pdf_url = row.get('pdf_url', '')
            code_url = row.get('code_url', '')

            # Format links
            code_link = f'[code]({code_url})' if code_url else ''
            paper_link = f'[pdf]({pdf_url})' if pdf_url else ''

            # Get GitHub info
            info = github_info.get(code_url, {})
            about = info.get('about', '').replace('|', '\\|').replace('\n', ' ')
            language = info.get('language', '')
            stars = info.get('stars', '')
            forks = info.get('forks', '')
            watches = info.get('watches', '')

            f.write(f'| {title} | {code_link} | {about} | {language} | {stars} | {forks} | {watches} | {paper_link} | |\n')

    print(f"Generated {out_path} with {len(rows)} papers")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 csv_to_md.py <csv_file>")
        sys.exit(1)

    csv_path = Path(sys.argv[1])
    if not csv_path.exists():
        print(f"Error: {csv_path} not found")
        sys.exit(1)

    csv_to_md(csv_path)


if __name__ == '__main__':
    main()
