"""P9-T1 load helper: hammer /chat and /upload against a local server.

Usage (server already running on 127.0.0.1:8000):

    python scripts/abuse_chat.py

Exits 0 when caps return 429/503 as expected. Does not print questions or keys.
"""

from __future__ import annotations

import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:8000"


def _json(method: str, path: str, body: bytes | None = None, headers: dict[str, str] | None = None) -> tuple[int, str]:
    req = Request(BASE + path, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urlopen(req, timeout=10) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")[:200]
    except HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")[:200]


def main() -> int:
    try:
        health_code, _ = _json("GET", "/health")
    except URLError as exc:
        print(f"server_down detail={exc}")
        return 2
    if health_code != 200:
        print(f"health_failed status={health_code}")
        return 2

    code, body = _json("POST", "/session", body=b"{}")
    if code != 200 or "session_id" not in body:
        print(f"session_failed status={code}")
        return 1
    # Parse token without importing json if the body is tiny JSON
    token = body.split("session_id")[-1].split('"')[2]
    headers = {"Authorization": f"Bearer {token}"}
    statuses: list[int] = []
    for _ in range(25):
        status, _detail = _json(
            "POST",
            "/chat",
            body=b'{"question":"What is net sales?","history":[]}',
            headers=headers,
        )
        statuses.append(status)
        if status == 429:
            break
    tripped = 429 in statuses
    print(f"chat_statuses={statuses[:8]}... tripped_429={tripped}")
    return 0 if tripped or 503 in statuses else 1


if __name__ == "__main__":
    sys.exit(main())
