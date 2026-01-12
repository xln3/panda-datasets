#!/usr/bin/env python3
"""
Base fetcher class for academic paper metadata scraping.
Provides common utilities for HTTP requests, code URL detection, and progress management.
"""

import re
import sys
import time
import json
import urllib.request
import urllib.error
from abc import ABC, abstractmethod
from html import unescape
from pathlib import Path
from typing import List, Dict, Optional

# Flush stdout immediately
sys.stdout.reconfigure(line_buffering=True)


class BaseFetcher(ABC):
    """Abstract base class for conference paper fetchers."""

    DELAY = 0.8  # Default delay between requests

    def __init__(self, name: str, output_dir: Path):
        self.name = name
        self.output_dir = Path(output_dir)
        self.output_file = self.output_dir / f"{name.lower()}_papers.csv"
        self.progress_file = self.output_dir / f"{name.lower()}_progress.json"

    def log(self, msg: str):
        """Print message with immediate flush."""
        print(msg, flush=True)

    def fetch_url(self, url: str, retries: int = 3) -> Optional[str]:
        """Fetch URL content with retries and error handling."""
        for attempt in range(retries):
            try:
                req = urllib.request.Request(url, headers={
                    'User-Agent': 'Mozilla/5.0 (research paper crawler)'
                })
                with urllib.request.urlopen(req, timeout=30) as response:
                    return response.read().decode('utf-8', errors='replace')
            except Exception as e:
                self.log(f"  Fetch failed ({attempt+1}): {e}")
                if attempt < retries - 1:
                    time.sleep(2)
        return None

    def is_valid_repo(self, url: str) -> bool:
        """Check if URL is a valid code repository."""
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

    def extract_code_url(self, text: str) -> Optional[str]:
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
                if self.is_valid_repo(url):
                    return url
        return None

    def has_code_mention(self, abstract: str) -> bool:
        """Check if abstract mentions code availability."""
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

    def fetch_arxiv_code(self, arxiv_url: str) -> Optional[str]:
        """Try to find code URL from arXiv page."""
        if not arxiv_url:
            return None

        arxiv_id = arxiv_url.split('/')[-1].split('v')[0]  # Handle vX versions
        html = self.fetch_url(f"https://arxiv.org/abs/{arxiv_id}")
        if not html:
            return None

        return self.extract_code_url(html)

    def load_progress(self) -> Dict:
        """Load progress from checkpoint file."""
        if self.progress_file.exists():
            with open(self.progress_file) as f:
                return json.load(f)
        return {'processed': [], 'last_index': 0}

    def save_progress(self, progress: Dict):
        """Save progress to checkpoint file."""
        with open(self.progress_file, 'w') as f:
            json.dump(progress, f, indent=2)

    def save_csv(self, papers: List[Dict]):
        """Save papers to CSV file."""
        with open(self.output_file, 'w', encoding='utf-8') as f:
            f.write('title,pdf_url,arxiv_url,code_available,code_url\n')
            for p in papers:
                title = p.get('title', '').replace('"', '""').replace(',', ';')
                pdf = p.get('pdf_url', '') or ''
                arxiv = p.get('arxiv_url', '') or ''
                code = p.get('code_url', '') or ''
                avail = 'yes' if code else ('maybe' if p.get('code_mentioned') else 'no')
                f.write(f'"{title}",{pdf},{arxiv},{avail},{code}\n')

    @abstractmethod
    def extract_papers(self) -> List[Dict]:
        """Extract paper list from conference proceedings.
        Returns list of dicts with at least 'title' and 'page_url' keys.
        """
        pass

    @abstractmethod
    def process_paper(self, paper: Dict) -> Dict:
        """Process a single paper to extract metadata.
        Returns dict with: title, pdf_url, arxiv_url, code_url, code_mentioned
        """
        pass

    def run(self):
        """Main execution loop with progress tracking."""
        self.log(f"{self.name} Paper Fetcher")
        self.log("=" * 50)

        papers = self.extract_papers()

        progress = self.load_progress()
        processed = progress['processed']
        start = progress['last_index']

        # Revalidate old entries
        for p in processed:
            if p.get('code_url') and not self.is_valid_repo(p['code_url']):
                p['code_url'] = None

        if start > 0:
            self.log(f"Resuming from paper {start}")

        for i, paper in enumerate(papers[start:], start=start):
            title_preview = paper['title'][:55] if len(paper['title']) > 55 else paper['title']
            self.log(f"[{i+1}/{len(papers)}] {title_preview}...")

            result = self.process_paper(paper)
            processed.append(result)

            if result.get('code_url'):
                self.log(f"  => Code: {result['code_url']}")
            elif result.get('code_mentioned'):
                self.log(f"  => (code mentioned but no URL)")

            if (i + 1) % 10 == 0:
                progress['processed'] = processed
                progress['last_index'] = i + 1
                self.save_progress(progress)
                self.save_csv(processed)
                self.log(f"  [Saved progress: {i+1} papers]")

            time.sleep(self.DELAY)

        # Final save
        progress['processed'] = processed
        progress['last_index'] = len(papers)
        self.save_progress(progress)
        self.save_csv(processed)

        with_code = sum(1 for p in processed if p.get('code_url'))
        maybe = sum(1 for p in processed if p.get('code_mentioned') and not p.get('code_url'))

        self.log(f"\nDone! {len(processed)} papers saved to {self.output_file}")
        self.log(f"With code URL: {with_code}")
        self.log(f"Code mentioned (no URL): {maybe}")
