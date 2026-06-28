"""
Batch downloader for PEMS Station 5-Minute data, District 4 (Bay Area).

Usage:
    python -m scripts.download_pems --cookie "your_cookie_string_here" --out data/pems/

The script:
1. Hits the Clearinghouse page to scrape all download links for the selected type/district
2. Downloads each .txt.gz file in sequence
3. Skips files already downloaded
"""

import argparse
import re
import time
from pathlib import Path

import httpx

BASE_URL = "https://pems.dot.ca.gov"
CLEARINGHOUSE_URL = f"{BASE_URL}/"


def scrape_download_ids(cookie: str, data_type: str = "station_5min", district: int = 4) -> list[tuple[str, str]]:
    """Returns list of (download_id, filename) for all available files."""
    params = {
        "dnode": "Clearinghouse",
        "type": data_type,
        "district_id": str(district),
        "submit": "Submit",
    }
    headers = {"Cookie": cookie, "User-Agent": "Mozilla/5.0"}

    with httpx.Client(timeout=30, follow_redirects=True) as client:
        resp = client.get(CLEARINGHOUSE_URL, params=params, headers=headers)
        resp.raise_for_status()

    # Extract all download links: href="?download=XXXXXX&dnode=Clearinghouse"
    pattern = r'\?download=(\d+)&amp;dnode=Clearinghouse[^"]*"[^>]*>([^<]+\.txt\.gz)'
    matches = re.findall(pattern, resp.text)

    if not matches:
        # Try alternate pattern without amp;
        pattern2 = r'\?download=(\d+)&dnode=Clearinghouse[^"]*"[^>]*>([^<]+\.txt\.gz)'
        matches = re.findall(pattern2, resp.text)

    return matches


def download_files(
    cookie: str,
    download_ids: list[tuple[str, str]],
    out_dir: Path,
    delay: float = 1.0,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    headers = {"Cookie": cookie, "User-Agent": "Mozilla/5.0"}
    total = len(download_ids)

    with httpx.Client(timeout=120, follow_redirects=True) as client:
        for i, (dl_id, filename) in enumerate(download_ids, 1):
            dest = out_dir / filename
            if dest.exists():
                print(f"[{i}/{total}] Skip (exists): {filename}")
                continue

            url = f"{BASE_URL}/?download={dl_id}&dnode=Clearinghouse"
            print(f"[{i}/{total}] Downloading {filename}...", end=" ", flush=True)
            try:
                resp = client.get(url, headers=headers)
                resp.raise_for_status()
                dest.write_bytes(resp.content)
                print(f"{len(resp.content) / 1024:.0f} KB")
            except Exception as e:
                print(f"FAILED: {e}")

            time.sleep(delay)  # be polite to the server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cookie", required=True, help="Full Cookie header value from browser DevTools")
    parser.add_argument("--out", default="data/pems", help="Output directory")
    parser.add_argument("--type", default="station_5min", help="PEMS data type (station_5min, station_meta)")
    parser.add_argument("--district", type=int, default=4, help="Caltrans district (4 = Bay Area)")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds between requests")
    args = parser.parse_args()

    print(f"Scraping file list for type={args.type}, district={args.district}...")
    files = scrape_download_ids(args.cookie, args.type, args.district)

    if not files:
        print("No files found. Check your cookie or data type.")
        return

    print(f"Found {len(files)} files. Downloading to {args.out}/")
    download_files(args.cookie, files, Path(args.out), delay=args.delay)
    print("Done.")


if __name__ == "__main__":
    main()
