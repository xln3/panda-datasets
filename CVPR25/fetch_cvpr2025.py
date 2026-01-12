#!/usr/bin/env python3
"""
Fetch CVPR 2025 paper list with code availability check.
Uses CVF Open Access Repository (same structure as ICCV).
"""

import re
import sys
import time
from html import unescape
from pathlib import Path

# Add parent directory to path for base_fetcher import
sys.path.insert(0, str(Path(__file__).parent.parent))
from base_fetcher import BaseFetcher


class CVPR2025Fetcher(BaseFetcher):
    """Fetcher for CVPR 2025 papers from CVF Open Access."""

    BASE_URL = "https://openaccess.thecvf.com"

    def __init__(self):
        super().__init__("CVPR2025", Path(__file__).parent)

    def extract_papers(self):
        """Extract paper list from CVF main listing page."""
        self.log("Fetching main listing...")
        html = self.fetch_url(f"{self.BASE_URL}/CVPR2025?day=all")
        if not html:
            raise Exception("Failed to fetch listing")

        pattern = r'<dt class="ptitle"><br><a href="([^"]+)">([^<]+)</a>'
        matches = re.findall(pattern, html)

        papers = [{'page_url': url, 'title': unescape(t).strip()} for url, t in matches]
        self.log(f"Found {len(papers)} papers")
        return papers

    def process_paper(self, paper):
        """Process a single paper to extract metadata."""
        html = self.fetch_url(self.BASE_URL + paper['page_url'])
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
    fetcher = CVPR2025Fetcher()
    fetcher.run()
