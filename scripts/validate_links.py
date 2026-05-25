#!/usr/bin/env python3
"""Script to validate links in the README.md file.

This script checks all URLs found in the README.md to ensure they are
accessible and return valid HTTP responses. It reports broken or
unreachable links for maintainers to review.
"""

import re
import sys
import time
import argparse
from pathlib import Path
from typing import Optional

import requests
from requests.exceptions import ConnectionError, Timeout, TooManyRedirects


DEFAULT_README = Path(__file__).parent.parent / "README.md"
URL_PATTERN = re.compile(r'https?://[^\s\)\]\>"]+', re.IGNORECASE)
REQUEST_TIMEOUT = 10  # seconds
RETRY_DELAY = 2  # seconds between retries
MAX_RETRIES = 2


def extract_urls(filepath: Path) -> list[str]:
    """Extract all URLs from the given file.

    Args:
        filepath: Path to the file to extract URLs from.

    Returns:
        A list of unique URLs found in the file.
    """
    content = filepath.read_text(encoding="utf-8")
    urls = URL_PATTERN.findall(content)
    # Remove trailing punctuation that may have been captured
    cleaned = [url.rstrip(".,;:") for url in urls]
    return list(dict.fromkeys(cleaned))  # preserve order, remove duplicates


def check_url(url: str, session: requests.Session, retries: int = MAX_RETRIES) -> tuple[bool, Optional[int], str]:
    """Check if a URL is reachable.

    Args:
        url: The URL to check.
        session: A requests Session object for connection pooling.
        retries: Number of retry attempts on failure.

    Returns:
        A tuple of (is_valid, status_code, message).
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; public-apis-link-checker/1.0)"
    }
    for attempt in range(retries + 1):
        try:
            response = session.head(
                url,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
                allow_redirects=True,
            )
            if response.status_code == 405:
                # HEAD not allowed, fall back to GET
                response = session.get(
                    url,
                    headers=headers,
                    timeout=REQUEST_TIMEOUT,
                    allow_redirects=True,
                    stream=True,
                )
            status = response.status_code
            if status < 400:
                return True, status, "OK"
            return False, status, f"HTTP {status}"
        except Timeout:
            if attempt < retries:
                time.sleep(RETRY_DELAY)
                continue
            return False, None, "Timeout"
        except ConnectionError as exc:
            if attempt < retries:
                time.sleep(RETRY_DELAY)
                continue
            return False, None, f"Connection error: {exc}"
        except TooManyRedirects:
            return False, None, "Too many redirects"
        except Exception as exc:  # pylint: disable=broad-except
            return False, None, f"Unexpected error: {exc}"
    return False, None, "Max retries exceeded"


def validate_links(filepath: Path, verbose: bool = False) -> int:
    """Validate all links in the given file.

    Args:
        filepath: Path to the file containing URLs.
        verbose: If True, print status for every URL checked.

    Returns:
        The number of broken links found.
    """
    urls = extract_urls(filepath)
    print(f"Found {len(urls)} unique URLs in {filepath}")

    broken = []
    with requests.Session() as session:
        for i, url in enumerate(urls, start=1):
            is_valid, status_code, message = check_url(url, session)
            if verbose or not is_valid:
                status_label = str(status_code) if status_code else "N/A"
                mark = "✓" if is_valid else "✗"
                print(f"[{i}/{len(urls)}] {mark} [{status_label}] {url} — {message}")
            if not is_valid:
                broken.append((url, message))

    if broken:
        print(f"\n{len(broken)} broken link(s) found:")
        for url, reason in broken:
            print(f"  - {url}  ({reason})")
    else:
        print("\nAll links are valid.")

    return len(broken)


def main() -> None:
    """Entry point for the link validation script."""
    parser = argparse.ArgumentParser(description="Validate URLs in README.md")
    parser.add_argument(
        "--file",
        type=Path,
        default=DEFAULT_README,
        help="Path to the file to validate (default: README.md)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print status for every URL, not just broken ones",
    )
    args = parser.parse_args()

    if not args.file.exists():
        print(f"Error: File not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    broken_count = validate_links(args.file, verbose=args.verbose)
    sys.exit(1 if broken_count > 0 else 0)


if __name__ == "__main__":
    main()
