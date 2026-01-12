#!/usr/bin/env python3
"""
Fetch ICRA 2025 paper list with code availability check.
Uses DBLP as the public data source for paper metadata.
"""

import re
import sys
import time
import urllib.parse
from html import unescape
from pathlib import Path

# Add parent directory to path for base_fetcher import
sys.path.insert(0, str(Path(__file__).parent.parent))
from base_fetcher import BaseFetcher


class ICRA2025Fetcher(BaseFetcher):
    """Fetcher for ICRA 2025 papers from DBLP."""

    DBLP_URL = "https://dblp.org"
    CONF_KEY = "conf/icra/icra2025"  # DBLP conference key

    def __init__(self):
        super().__init__("ICRA2025", Path(__file__).parent)

    def extract_papers(self):
        """Extract paper list from DBLP."""
        self.log("Fetching DBLP listing...")

        # DBLP HTML page for the conference
        html = self.fetch_url(f"{self.DBLP_URL}/db/conf/icra/icra2025.html")
        if not html:
            raise Exception("Failed to fetch DBLP listing")

        papers = []

        # DBLP format: titles are in <span class="title" itemprop="name">TITLE</span>
        # DOIs follow a pattern near the title

        # Extract all title spans
        title_pattern = r'<span class="title"[^>]*itemprop="name"[^>]*>([^<]+)</span>'
        titles = re.findall(title_pattern, html)

        # Extract DOI links - they appear in order matching titles
        doi_pattern = r'href="(https://doi\.org/10\.1109/ICRA[^"]+)"'
        dois = re.findall(doi_pattern, html)

        self.log(f"Found {len(titles)} titles and {len(dois)} DOIs")

        # Skip the first title if it's the venue title
        if titles and 'IEEE International Conference on Robotics' in titles[0]:
            titles = titles[1:]

        # Match titles with DOIs
        for i, title in enumerate(titles):
            title = unescape(title).strip()
            if title.endswith('.'):
                title = title[:-1]

            # Get corresponding DOI if available
            page_url = dois[i] if i < len(dois) else ''

            papers.append({
                'title': title,
                'page_url': page_url,
                'arxiv_url': None,  # Will be searched in process_paper
            })

        self.log(f"Found {len(papers)} papers from DBLP")
        return papers

    def _search_arxiv(self, title):
        """Search arXiv for paper by title."""
        # Use arXiv API to search for the paper
        query = urllib.parse.quote(f'ti:"{title}"')
        search_url = f"https://export.arxiv.org/api/query?search_query={query}&max_results=1"

        xml = self.fetch_url(search_url)
        if not xml:
            return None, None

        # Parse simple XML response
        # Look for <id> (arXiv URL) and <summary> (abstract)
        id_match = re.search(r'<id>(https?://arxiv\.org/abs/[^<]+)</id>', xml)
        summary_match = re.search(r'<summary>([^<]+)</summary>', xml, re.DOTALL)

        arxiv_url = id_match.group(1) if id_match else None
        abstract = summary_match.group(1).strip() if summary_match else None

        # Verify title match (avoid false positives)
        if arxiv_url:
            title_match = re.search(r'<title>([^<]+)</title>', xml)
            if title_match:
                found_title = title_match.group(1).strip().lower()
                query_title = title.lower()
                # Simple similarity check
                if query_title[:30] not in found_title and found_title[:30] not in query_title:
                    return None, None

        return arxiv_url, abstract

    def process_paper(self, paper):
        """Process a single paper to extract metadata."""
        title = paper['title']
        arxiv_url = paper.get('arxiv_url')
        abstract = None
        code_url = None

        # If no arXiv URL from DBLP, search arXiv
        if not arxiv_url:
            time.sleep(1.0)  # Rate limit for arXiv API
            arxiv_url, abstract = self._search_arxiv(title)

        # If we have arXiv URL, fetch the page for code links
        if arxiv_url and not abstract:
            time.sleep(self.DELAY)
            arxiv_html = self.fetch_url(arxiv_url)
            if arxiv_html:
                # Extract abstract from arXiv page
                abs_match = re.search(r'<blockquote[^>]*class="abstract[^"]*"[^>]*>\s*<span[^>]*>Abstract:</span>\s*(.*?)\s*</blockquote>', arxiv_html, re.DOTALL | re.IGNORECASE)
                if abs_match:
                    abstract = unescape(abs_match.group(1)).strip()
                    abstract = re.sub(r'<[^>]+>', '', abstract).strip()

                # Look for code links
                code_url = self.extract_code_url(arxiv_html)

        # Check abstract for code
        if not code_url and abstract:
            code_url = self.extract_code_url(abstract)

        code_mentioned = self.has_code_mention(abstract) if abstract else False

        # PDF URL - use DOI/IEEE link if available
        pdf_url = paper.get('page_url', '')

        return {
            'title': title,
            'pdf_url': pdf_url,
            'arxiv_url': arxiv_url,
            'code_url': code_url,
            'code_mentioned': code_mentioned,
        }


if __name__ == '__main__':
    fetcher = ICRA2025Fetcher()
    fetcher.run()
