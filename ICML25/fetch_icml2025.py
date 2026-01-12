#!/usr/bin/env python3
"""
Fetch ICML 2025 paper list with code availability check.
Uses PMLR (Proceedings of Machine Learning Research) format.
"""

import re
import sys
import time
from html import unescape
from pathlib import Path

# Add parent directory to path for base_fetcher import
sys.path.insert(0, str(Path(__file__).parent.parent))
from base_fetcher import BaseFetcher


class ICML2025Fetcher(BaseFetcher):
    """Fetcher for ICML 2025 papers from PMLR."""

    BASE_URL = "https://proceedings.mlr.press"
    VOLUME = "v267"

    def __init__(self):
        super().__init__("ICML2025", Path(__file__).parent)

    def extract_papers(self):
        """Extract paper list from PMLR volume page."""
        self.log("Fetching main listing...")
        html = self.fetch_url(f"{self.BASE_URL}/{self.VOLUME}/")
        if not html:
            raise Exception("Failed to fetch listing")

        papers = []

        # PMLR format: papers are in <div class="paper"> blocks
        # Each block has: <p class="title">TITLE</p>, <p class="details">...</p>, <p class="links">...</p>
        paper_pattern = r'<div class="paper">\s*<p class="title">([^<]+)</p>\s*<p class="details">.*?</p>\s*<p class="links">(.*?)</p>'
        matches = re.findall(paper_pattern, html, re.DOTALL)

        for title, links_html in matches:
            title = unescape(title).strip()

            # Extract abstract page URL from links
            abs_match = re.search(r'href="([^"]+)"[^>]*>abs<', links_html)
            page_url = abs_match.group(1) if abs_match else None

            # Extract software URL directly from listing page
            software_match = re.search(r'href="([^"]+)"[^>]*>Software<', links_html)
            software_url = software_match.group(1) if software_match else None

            # Extract PDF URL
            pdf_match = re.search(r'href="([^"]+)"[^>]*>Download PDF<', links_html)
            pdf_url = pdf_match.group(1) if pdf_match else None

            papers.append({
                'page_url': page_url,
                'title': title,
                'software_url': software_url,
                'pdf_url': pdf_url,
            })

        self.log(f"Found {len(papers)} papers")
        return papers

    def process_paper(self, paper):
        """Process a single paper to extract metadata."""
        # Use pre-extracted data from listing page
        pdf_url = paper.get('pdf_url')
        software_url = paper.get('software_url')

        # Check if software URL is valid repo
        code_url = None
        if software_url and self.is_valid_repo(software_url):
            code_url = software_url

        # Fetch abstract page for more details
        abstract = None
        arxiv_url = None

        if paper.get('page_url'):
            page_url = paper['page_url']
            if not page_url.startswith('http'):
                page_url = f"{self.BASE_URL}{page_url}"

            html = self.fetch_url(page_url)
            if html:
                # Abstract
                m = re.search(r'<div[^>]*class="abstract"[^>]*>\s*(.*?)\s*</div>', html, re.DOTALL | re.IGNORECASE)
                if not m:
                    m = re.search(r'<h[23][^>]*>Abstract</h[23]>\s*<p>(.*?)</p>', html, re.DOTALL | re.IGNORECASE)
                if not m:
                    m = re.search(r'<div[^>]*id="abstract"[^>]*>(.*?)</div>', html, re.DOTALL | re.IGNORECASE)
                abstract = unescape(m.group(1).strip()) if m else None

                # Clean up abstract HTML tags
                if abstract:
                    abstract = re.sub(r'<[^>]+>', '', abstract).strip()

                # arXiv link
                m = re.search(r'href="(https?://arxiv\.org/abs/[^"]+)"', html)
                arxiv_url = m.group(1) if m else None

                # Try to extract code from page if not found yet
                if not code_url:
                    code_url = self.extract_code_url(html)

        # Try to extract from abstract
        if not code_url and abstract:
            code_url = self.extract_code_url(abstract)

        code_mentioned = self.has_code_mention(abstract)

        # If still no code but has arXiv, check arXiv
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
    fetcher = ICML2025Fetcher()
    fetcher.run()
