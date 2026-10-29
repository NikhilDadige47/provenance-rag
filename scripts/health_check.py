"""P9-T5 uptime probe: hit /health and fail if the process is not ready.

Privacy-safe: prints only status codes and component names, never content.

Usage (server already running):

    python scripts/health_check.py
    python scripts/health_check.py http://127.0.0.1:8000
"""

from __future__ import annotations

import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_BASE = "http://127.0.0.1:8000"


def _get(url: str) -> tuple[int, dict]:
    req = Request(url, method="GET")
    try:
        with urlopen(req, timeout=8) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = {}
            return resp.status, payload if isinstance(payload, dict) else {}
    except HTTPError as exc:
        return exc.code, {}


def main() -> int:
    base = (sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE).rstrip("/")
    try:
        code, body = _get(base + "/health")
    except URLError as exc:
        print(f"health_down detail={type(exc).__name__}")
        return 2
    ready = bool(body.get("ready"))
    components = body.get("components") if isinstance(body.get("components"), dict) else {}
    names = ",".join(f"{key}={value}" for key, value in sorted(components.items()))
    print(f"health status={code} ready={ready} components={names or 'none'}")
    if code != 200 or not ready:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
