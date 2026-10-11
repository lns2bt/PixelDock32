#!/usr/bin/env python3
"""Collect passive transport telemetry. Does not select content or change LEDs."""

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Do not forward the access token to a redirect destination.
        return None


def positive_number(value):
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise argparse.ArgumentTypeError("must be a finite number > 0")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="PixelDock32 base URL (prefer localhost via SSH)")
    parser.add_argument("--duration", type=positive_number, default=600, help="seconds (default: 600)")
    parser.add_argument("--interval", type=positive_number, default=1, help="seconds between samples")
    parser.add_argument("--output", type=Path, required=True, help="new JSONL file; existing files are never overwritten")
    args = parser.parse_args()
    parsed = urlparse(args.url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        parser.error("provide a plain HTTP(S) base URL without credentials, query or fragment")
    token = os.environ.get("PIXELDOCK_TOKEN", "").strip()
    if not token:
        parser.error("set PIXELDOCK_TOKEN to a login access token (not a command-line argument)")
    endpoint = args.url.rstrip("/") + "/api/debug/led/metrics"
    opener = build_opener(NoRedirect())
    started = time.monotonic()
    next_sample = started
    successes = 0
    failures = 0
    try:
        with args.output.open("x", encoding="utf-8") as output:
            while time.monotonic() - started < args.duration:
                request = Request(endpoint, headers={"Authorization": f"Bearer {token}"})
                try:
                    with opener.open(request, timeout=5) as response:
                        metrics = json.load(response)
                    record = {"metrics": metrics}
                    successes += 1
                except HTTPError as exc:
                    record = {"error": f"HTTP {exc.code}"}
                    failures += 1
                    exc.close()
                except (URLError, OSError, ValueError) as exc:
                    record = {"error": type(exc).__name__}
                    failures += 1
                record.update(timestamp=datetime.now(timezone.utc).isoformat(), elapsed_seconds=round(time.monotonic() - started, 3))
                output.write(json.dumps(record) + "\n")
                output.flush()
                next_sample += args.interval
                now = time.monotonic()
                if next_sample <= now:
                    next_sample = now + args.interval
                time.sleep(max(0, min(next_sample, started + args.duration) - now))
    except KeyboardInterrupt:
        print("Measurement interrupted; collected samples are retained.")
    except OSError as exc:
        parser.exit(1, f"Cannot create/write output file: {exc}\n")
    print(f"Samples: {successes} successful, {failures} failed. Output: {args.output}")
    return 0 if successes and not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
