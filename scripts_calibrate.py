"""Quick helper to call debug patterns from CLI while wiring panels."""

import argparse
import json
import urllib.request


def login(base_url: str, username: str, password: str) -> str:
    payload = json.dumps({"username": username, "password": password}).encode()
    req = urllib.request.Request(
        f"{base_url}/api/auth/login",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())
        return data["access_token"]


def set_pattern(base_url: str, token: str, pattern: str, seconds: int, interval_ms: int):
    payload = json.dumps(
        {"pattern": pattern, "seconds": seconds, "interval_ms": interval_ms}
    ).encode()
    req = urllib.request.Request(
        f"{base_url}/api/debug/pattern",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10):
        return


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="admin1234")
    parser.add_argument("--pattern", default="pixel_walk", choices=["pixel_walk", "panel_walk", "stripes", "border"])
    parser.add_argument("--seconds", type=int, default=20)
    parser.add_argument("--interval-ms", type=int, default=250)
    args = parser.parse_args()

    token = login(args.base_url, args.username, args.password)
    set_pattern(args.base_url, token, args.pattern, args.seconds, args.interval_ms)
    print("debug pattern started")
