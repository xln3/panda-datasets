#!/usr/bin/env python3
"""
Fetch ICCV 2025 paper list with code availability check.
"""

import re
import sys
import time
import json
import urllib.request
import urllib.error
from html import unescape
from pathlib import Path

BASE_URL = "https://openaccess.thecvf.com"
OUTPUT_FILE = Path("./iccv2025_papers.csv")
PROGRESS_FILE = Path("./iccv2025_progress.json")
DELAY = 0.8

# Flush stdout immediately
sys.stdout.reconfigure(line_buffering=True)

def log(msg):
    print(msg, flush=True)

def fetch_url(url, retries=3):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (research paper crawler)'
            })
            with urllib.request.urlopen(req, timeout=30) as response:
                return response.read().decode('utf-8', errors='replace')
        except Exception as e:
            log(f"  Fetch failed ({attempt+1}): {e}")
            if attempt < retries - 1:
                time.sleep(2)
    return None

def extract_papers():
    log("Fetching main listing...")
    html = fetch_url(f"{BASE_URL}/ICCV2025?day=all")
    if not html:
        raise Exception("Failed to fetch listing")
    
    pattern = r'<dt class="ptitle"><br><a href="([^"]+)">([^<]+)</a>'
    matches = re.findall(pattern, html)
    
    papers = [{'page_url': url, 'title': unescape(t).strip()} for url, t in matches]
    log(f"Found {len(papers)} papers")
    return papers

def is_valid_repo(url):
    """Only accept URLs that are clearly code repos."""
    if not url:
        return False
    
    # Reject common false positives
    rejects = [
        'huggingface.co/huggingface',
        'huggingface.co/docs',
        'huggingface.co/blog',
        'huggingface.co/join',
        'huggingface.co/pricing',
        'github.com/github',
        'github.com/features',
        'github.com/explore',
        '/arxiv.',
    ]
    for r in rejects:
        if r in url.lower():
            return False
    
    # Must match: github.com/org/repo or huggingface.co/org/repo
    # where org and repo are actual names (not docs, spaces without name, etc)
    patterns = [
        r'^https?://github\.com/([a-zA-Z0-9_-]+)/([a-zA-Z0-9_.-]+)(?:/|$)',
        r'^https?://gitlab\.com/([a-zA-Z0-9_-]+)/([a-zA-Z0-9_.-]+)(?:/|$)',
        r'^https?://huggingface\.co/spaces/([a-zA-Z0-9_-]+)/([a-zA-Z0-9_.-]+)(?:/|$)',
        r'^https?://huggingface\.co/([a-zA-Z0-9_-]+)/([a-zA-Z0-9_.-]+)(?:/|$)',
    ]
    
    for p in patterns:
        m = re.match(p, url)
        if m:
            org, repo = m.groups()
            # Reject generic org names
            if org.lower() in ['docs', 'blog', 'api', 'hub', 'join', 'huggingface']:
                return False
            return True
    
    return False

def extract_code_url(text):
    """Extract first valid code repo URL from text."""
    if not text:
        return None
    
    patterns = [
        r'https?://github\.com/[^\s<>"\')\]]+',
        r'https?://gitlab\.com/[^\s<>"\')\]]+',
        r'https?://huggingface\.co/[^\s<>"\')\]]+',
    ]
    
    for p in patterns:
        for m in re.findall(p, text, re.IGNORECASE):
            url = m.rstrip('.,;:')
            if is_valid_repo(url):
                return url
    return None

def has_code_mention(abstract):
    if not abstract:
        return False
    patterns = [
        r'code.{0,20}(available|released?|at|github)',
        r'(available|released?).{0,20}code',
        r'open.?sourc',
        r'our code',
        r'source code',
    ]
    return any(re.search(p, abstract, re.IGNORECASE) for p in patterns)

def fetch_arxiv_code(arxiv_url):
    if not arxiv_url:
        return None
    
    arxiv_id = arxiv_url.split('/')[-1].split('v')[0]  # Handle vX versions
    html = fetch_url(f"https://arxiv.org/abs/{arxiv_id}")
    if not html:
        return None
    
    # Look for code links in the page
    return extract_code_url(html)

def process_paper(paper):
    html = fetch_url(BASE_URL + paper['page_url'])
    if not html:
        return {**paper, 'error': 'fetch failed'}
    
    # PDF
    m = re.search(r'citation_pdf_url" content="([^"]+)"', html)
    pdf_url = m.group(1) if m else None
    
    # Abstract
    m = re.search(r'<div id="abstract">\s*(.*?)\s*</div>', html, re.DOTALL)
    abstract = unescape(m.group(1).strip()) if m else None
    
    # arXiv
    m = re.search(r'href="(https?://arxiv\.org/abs/[^"]+)"', html)
    arxiv_url = m.group(1) if m else None
    
    # Code from abstract
    code_url = extract_code_url(abstract)
    code_mentioned = has_code_mention(abstract)
    
    # If no code found but has arXiv, check arXiv page
    if not code_url and arxiv_url:
        time.sleep(DELAY)
        code_url = fetch_arxiv_code(arxiv_url)
    
    return {
        'title': paper['title'],
        'pdf_url': pdf_url,
        'arxiv_url': arxiv_url,
        'code_url': code_url,
        'code_mentioned': code_mentioned,
    }

def load_progress():
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {'processed': [], 'last_index': 0}

def save_progress(progress):
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(progress, f, indent=2)

def save_csv(papers):
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write('title,pdf_url,arxiv_url,code_available,code_url\n')
        for p in papers:
            title = p.get('title', '').replace('"', '""').replace(',', ';')
            pdf = p.get('pdf_url', '') or ''
            arxiv = p.get('arxiv_url', '') or ''
            code = p.get('code_url', '') or ''
            avail = 'yes' if code else ('maybe' if p.get('code_mentioned') else 'no')
            f.write(f'"{title}",{pdf},{arxiv},{avail},{code}\n')

def main():
    log("ICCV 2025 Paper Fetcher v2")
    log("=" * 50)
    
    papers = extract_papers()
    
    progress = load_progress()
    processed = progress['processed']
    start = progress['last_index']
    
    # Revalidate old entries
    for p in processed:
        if p.get('code_url') and not is_valid_repo(p['code_url']):
            p['code_url'] = None
    
    # Reset if too many invalid
    invalid = sum(1 for p in processed if p.get('code_url') and 'huggingface.co/docs' in p.get('code_url', ''))
    if invalid > 5:
        log(f"Found {invalid} invalid entries, restarting...")
        processed = []
        start = 0
    
    if start > 0:
        log(f"Resuming from paper {start}")
    
    for i, paper in enumerate(papers[start:], start=start):
        log(f"[{i+1}/{len(papers)}] {paper['title'][:55]}...")
        
        result = process_paper(paper)
        processed.append(result)
        
        if result.get('code_url'):
            log(f"  => Code: {result['code_url']}")
        elif result.get('code_mentioned'):
            log(f"  => (code mentioned but no URL)")
        
        if (i + 1) % 10 == 0:
            progress['processed'] = processed
            progress['last_index'] = i + 1
            save_progress(progress)
            save_csv(processed)
            log(f"  [Saved progress: {i+1} papers]")
        
        time.sleep(DELAY)
    
    # Final save
    progress['processed'] = processed
    progress['last_index'] = len(papers)
    save_progress(progress)
    save_csv(processed)
    
    with_code = sum(1 for p in processed if p.get('code_url'))
    maybe = sum(1 for p in processed if p.get('code_mentioned') and not p.get('code_url'))
    
    log(f"\nDone! {len(processed)} papers saved to {OUTPUT_FILE}")
    log(f"With code URL: {with_code}")
    log(f"Code mentioned (no URL): {maybe}")

if __name__ == '__main__':
    main()
