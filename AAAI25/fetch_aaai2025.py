#!/usr/bin/env python3
"""
Fetch AAAI 2025 paper list with code availability check.
Uses AAAI's OJS (Open Journal Systems) platform.
"""

import re
import sys
import time
from html import unescape
from pathlib import Path

# Add parent directory to path for base_fetcher import
sys.path.insert(0, str(Path(__file__).parent.parent))
from base_fetcher import BaseFetcher


class AAAI2025Fetcher(BaseFetcher):
    """Fetcher for AAAI 2025 papers from OJS."""

    BASE_URL = "https://ojs.aaai.org"
    JOURNAL_PATH = "/index.php/AAAI"
    VOLUME = 39  # AAAI-25 is Volume 39

    def __init__(self):
        super().__init__("AAAI2025", Path(__file__).parent)

    def _get_issue_urls(self):
        """Get all issue URLs for the volume."""
        # First, get the archive page to find all issues for Vol. 39
        archive_url = f"{self.BASE_URL}{self.JOURNAL_PATH}/issue/archive"
        html = self.fetch_url(archive_url)
        if not html:
            raise Exception("Failed to fetch archive page")

        # Find all issues for Vol. 39
        # Pattern: href="/index.php/AAAI/issue/view/XXX" with Vol. 39 nearby
        issue_urls = []

        # Look for issue links that mention Vol. 39
        pattern = r'href="(/index\.php/AAAI/issue/view/\d+)"[^>]*>.*?Vol\.\s*39'
        matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)

        # Alternative: look for AAAI-25 mentions
        if not matches:
            pattern = r'href="(/index\.php/AAAI/issue/view/(\d+))"'
            all_issues = re.findall(pattern, html)
            # Filter to likely Vol. 39 issues (usually higher issue IDs for recent volumes)
            # AAAI-24 was Vol. 38, so Vol. 39 issue IDs should be newer
            for url, issue_id in all_issues:
                # Check if this issue is Vol. 39 by fetching its page
                full_url = f"{self.BASE_URL}{url}"
                issue_html = self.fetch_url(full_url)
                if issue_html and ('Vol. 39' in issue_html or 'AAAI-25' in issue_html):
                    issue_urls.append(url)
                    self.log(f"  Found issue: {url}")
                time.sleep(0.3)

        return list(set(matches if matches else issue_urls))

    def extract_papers(self):
        """Extract paper list from all AAAI-25 issues."""
        self.log("Finding AAAI-25 issues from archive...")

        # Fetch archive page
        archive_url = f"{self.BASE_URL}{self.JOURNAL_PATH}/issue/archive"
        html = self.fetch_url(archive_url)
        if not html:
            raise Exception("Failed to fetch archive page")

        # Find all Vol. 39 issue URLs
        # Pattern: href="...issue/view/XXX" followed by Vol. 39
        issue_pattern = r'href="(https://ojs\.aaai\.org/index\.php/AAAI/issue/view/(\d+))"[^>]*>.*?Vol\.\s*39'
        matches = re.findall(issue_pattern, html, re.DOTALL)

        # Deduplicate
        issue_urls = list(set(url for url, _ in matches))
        self.log(f"Found {len(issue_urls)} AAAI-25 issues")

        papers = []

        for issue_url in issue_urls:
            self.log(f"Processing {issue_url}...")
            issue_html = self.fetch_url(issue_url)
            if not issue_html:
                continue

            # Extract papers from issue page
            # OJS format: <h3 class="title"><a href="URL">TITLE</a></h3>
            # or article-summary with title link

            # Pattern 1: title class links
            paper_pattern = r'<h3[^>]*class="title"[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>([^<]+)</a>'
            paper_matches = re.findall(paper_pattern, issue_html, re.DOTALL)

            # Pattern 2: article-summary blocks
            if not paper_matches:
                paper_pattern = r'class="obj_article_summary"[^>]*>.*?<a[^>]*href="([^"]+)"[^>]*class="[^"]*title[^"]*"[^>]*>([^<]+)</a>'
                paper_matches = re.findall(paper_pattern, issue_html, re.DOTALL)

            # Pattern 3: any link to article/view
            if not paper_matches:
                paper_pattern = r'<a[^>]*href="(https://ojs\.aaai\.org/index\.php/AAAI/article/view/\d+)"[^>]*>([^<]{10,})</a>'
                paper_matches = re.findall(paper_pattern, issue_html)

            for url, title in paper_matches:
                title = unescape(title).strip()
                # Skip empty or very short titles, and navigation links
                if not title or len(title) < 10:
                    continue
                if 'PDF' in title or 'Abstract' in title:
                    continue

                papers.append({
                    'page_url': url,
                    'title': title
                })

            time.sleep(0.5)

        # Deduplicate papers by title
        seen_titles = set()
        unique_papers = []
        for p in papers:
            if p['title'] not in seen_titles:
                seen_titles.add(p['title'])
                unique_papers.append(p)

        self.log(f"Found {len(unique_papers)} unique papers from {len(issue_urls)} issues")
        return unique_papers

    def process_paper(self, paper):
        """Process a single paper to extract metadata."""
        html = self.fetch_url(paper['page_url'])
        if not html:
            return {**paper, 'error': 'fetch failed'}

        # PDF URL
        m = re.search(r'href="([^"]+)"[^>]*class="[^"]*pdf[^"]*"', html, re.IGNORECASE)
        if not m:
            m = re.search(r'href="([^"]+/\d+/\d+)"[^>]*>.*?PDF', html, re.IGNORECASE)
        if not m:
            m = re.search(r'href="([^"]+\.pdf)"', html, re.IGNORECASE)
        pdf_url = m.group(1) if m else None

        # Abstract
        m = re.search(r'<section[^>]*class="[^"]*abstract[^"]*"[^>]*>\s*<h2[^>]*>Abstract</h2>\s*<p>(.*?)</p>', html, re.DOTALL | re.IGNORECASE)
        if not m:
            m = re.search(r'<div[^>]*class="[^"]*abstract[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL | re.IGNORECASE)
        if not m:
            m = re.search(r'name="DC\.Description"[^>]*content="([^"]+)"', html, re.IGNORECASE)
        abstract = unescape(m.group(1).strip()) if m else None

        # Clean up abstract HTML tags
        if abstract:
            abstract = re.sub(r'<[^>]+>', '', abstract).strip()

        # arXiv link (often in abstract or supplementary links)
        m = re.search(r'href="(https?://arxiv\.org/abs/[^"]+)"', html)
        arxiv_url = m.group(1) if m else None

        # Code URL from page
        code_url = self.extract_code_url(html)

        # Code from abstract
        if not code_url:
            code_url = self.extract_code_url(abstract)

        code_mentioned = self.has_code_mention(abstract)

        # If no code found but has arXiv, check arXiv page
        if not code_url and arxiv_url:
            time.sleep(self.DELAY)
            code_url = self.fetch_arxiv_code(arxiv_url)

        return {
            'title': paper['title'],
            'pdf_url': pdf_url,
            'arxiv_url': arxiv_url,
            'code_url': code_url,
            'code_mentioned': code_mentioned,
        }


if __name__ == '__main__':
    fetcher = AAAI2025Fetcher()
    fetcher.run()
