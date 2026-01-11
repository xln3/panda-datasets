#!/usr/bin/env python3
"""
Convert conference paper CSV to Markdown table.

Usage:
    python3 csv_to_md.py ICCV25/iccv2025_papers.csv
    # Output: ICCV25/papers_iccv25.md
"""

import csv
import sys
import re
from pathlib import Path


def csv_to_md(csv_path: Path) -> None:
    # Derive output filename from directory name
    conf_dir = csv_path.parent
    conf_name = conf_dir.name.lower()  # e.g., "ICCV25" -> "iccv25"
    out_path = conf_dir / f"papers_{conf_name}.md"

    rows = []
    with open(csv_path, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            code_avail = row.get('code_available', '').strip()
            code_url = row.get('code_url', '').strip()
            # Filter: keep if has code_url OR code_available is yes/maybe
            if code_url or code_avail in ('yes', 'maybe'):
                rows.append(row)

    # Write markdown
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('| title | pdf_url | code_available | code_url | pass^4 |\n')
        f.write('|-------|---------|----------------|----------|--------|\n')
        for row in rows:
            title = row.get('title', '').replace('|', '\\|')
            pdf_url = row.get('pdf_url', '')
            code_avail = row.get('code_available', '')
            code_url = row.get('code_url', '')
            f.write(f'| {title} | {pdf_url} | {code_avail} | {code_url} | |\n')

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
