"""Production smoke test for Tiers A, B, and C against one public origin.

Usage:

    python scripts/smoke_prod.py
    python scripts/smoke_prod.py https://your-service.onrender.com

Environment:
    SMOKE_BASE_URL      Default http://127.0.0.1:8000 (or the CLI argument)
    SMOKE_LLM_KEY       Optional visitor LLM key for Tier C
    SMOKE_LLM_PROVIDER  Optional, default groq
    SMOKE_LLM_MODEL     Optional

Prints pass/fail only. Never prints questions, document text, or keys.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_BASE = "http://127.0.0.1:8000"
JOB_WAIT_SECONDS = 180
CHAT_TIMEOUT = 90

# Minimal one-page PDF that passes server-side magic-byte validation.
_SMOKE_PDF = (
    b"%PDF-1.1\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R"
    b"/Resources<</Font<</F1 4 0 R>>>>/Contents 5 0 R>>endobj\n"
    b"4 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
    b"5 0 obj<</Length 84>>stream\n"
    b"BT /F1 18 Tf 72 720 Td (Smoke test quarterly revenue increased 22 percent) Tj ET\n"
    b"endstream\nendobj\n"
    b"xref\n0 6\n0000000000 65535 f \n0000000009 00000 n \n"
    b"0000000058 00000 n \n0000000115 00000 n \n0000000274 00000 n \n"
    b"0000000341 00000 n \ntrailer<</Size 6/Root 1 0 R>>\nstartxref\n475\n%%EOF\n"
)


class SmokeFailure(RuntimeError):
    """A named smoke step failed."""


def _request(
    base: str,
    method: str,
    path: str,
    *,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
) -> tuple[int, dict | str]:
    req = Request(base + path, data=body, method=method)
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                parsed: dict | str = json.loads(raw)
            except json.JSONDecodeError:
                parsed = raw[:200]
            return resp.status, parsed
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = raw[:200]
        return exc.code, parsed


def _json_headers(token: str | None = None, extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if extra:
        headers.update(extra)
    return headers


def _require_ok(step: str, code: int, body: dict | str, expected: int = 200) -> dict:
    if code != expected or not isinstance(body, dict):
        raise SmokeFailure(f"{step} status={code}")
    return body


def _new_session(base: str) -> str:
    code, body = _request(base, "POST", "/session", body=b"{}", headers=_json_headers())
    payload = _require_ok("session", code, body)
    token = str(payload.get("session_id") or "")
    if not token:
        raise SmokeFailure("session_missing_token")
    return token


def _chat(base: str, token: str, question: str, extra: dict[str, str] | None = None) -> dict:
    payload = json.dumps({"question": question, "history": []}).encode()
    code, body = _request(
        base,
        "POST",
        "/chat",
        body=payload,
        headers=_json_headers(token, extra),
        timeout=CHAT_TIMEOUT,
    )
    return _require_ok("chat", code, body)


def _upload(base: str, token: str) -> str:
    boundary = f"----smoke{uuid.uuid4().hex}"
    filename = "smoke-test.pdf"
    parts = [
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="parser"\r\n\r\n'
            f"local_pymupdf\r\n"
        ).encode(),
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="terms_accepted"\r\n\r\n'
            f"true\r\n"
        ).encode(),
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: application/pdf\r\n\r\n"
        ).encode()
        + _SMOKE_PDF
        + b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ]
    body = b"".join(parts)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Accept": "application/json",
    }
    code, payload = _request(base, "POST", "/upload", body=body, headers=headers, timeout=60)
    data = _require_ok("upload", code, payload, expected=202)
    job_id = str(data.get("job_id") or "")
    if not job_id:
        raise SmokeFailure("upload_missing_job")
    return job_id


def _wait_job(base: str, token: str, job_id: str) -> dict:
    deadline = time.monotonic() + JOB_WAIT_SECONDS
    last_status = "unknown"
    while time.monotonic() < deadline:
        code, body = _request(
            base,
            "GET",
            f"/jobs/{job_id}",
            headers=_json_headers(token),
            timeout=20,
        )
        if code != 200 or not isinstance(body, dict):
            raise SmokeFailure(f"job_poll status={code}")
        last_status = str(body.get("status") or "unknown")
        if last_status == "ready":
            return body
        if last_status == "failed":
            raise SmokeFailure("job_failed")
        time.sleep(2)
    raise SmokeFailure(f"job_timeout status={last_status}")


def _tier_a(base: str) -> None:
    token = _new_session(base)
    code, body = _request(base, "GET", "/examples", headers=_json_headers())
    payload = _require_ok("examples", code, body)
    examples = payload.get("examples") if isinstance(payload.get("examples"), list) else []
    question = "What is this document about?"
    for item in examples:
        if isinstance(item, str) and item.strip():
            question = item.strip()
            break
        if not isinstance(item, dict):
            continue
        if str(item.get("category") or "") == "not_found":
            continue
        candidate = str(item.get("question") or item.get("chip") or "").strip()
        if candidate:
            question = candidate
            break
    result = _chat(base, token, question)
    if not result.get("answer"):
        raise SmokeFailure("tier_a_empty_answer")
    print("tier_a pass")


def _tier_b(base: str) -> None:
    token = _new_session(base)
    job_id = _upload(base, token)
    _wait_job(base, token, job_id)
    result = _chat(base, token, "What does this document say about quarterly revenue?")
    if not result.get("answer"):
        raise SmokeFailure("tier_b_empty_answer")
    code, _body = _request(base, "DELETE", "/session", headers=_json_headers(token))
    if code != 200:
        raise SmokeFailure(f"tier_b_delete status={code}")
    print("tier_b pass")


def _tier_c(base: str, llm_key: str, provider: str, model: str | None) -> None:
    token = _new_session(base)
    job_id = _upload(base, token)
    _wait_job(base, token, job_id)
    extra = {"X-LLM-Key": llm_key, "X-LLM-Provider": provider}
    if model:
        extra["X-LLM-Model"] = model
    result = _chat(base, token, "Summarize the smoke test document in one sentence.", extra)
    if not result.get("used_visitor_key"):
        raise SmokeFailure("tier_c_owner_llm_used")
    if not result.get("answer"):
        raise SmokeFailure("tier_c_empty_answer")
    code, _body = _request(base, "DELETE", "/session", headers=_json_headers(token))
    if code != 200:
        raise SmokeFailure(f"tier_c_delete status={code}")
    print("tier_c pass")


def main() -> int:
    arg_url = sys.argv[1] if len(sys.argv) > 1 else ""
    base = (arg_url or os.environ.get("SMOKE_BASE_URL") or DEFAULT_BASE).rstrip("/")
    try:
        code, body = _request(base, "GET", "/health", timeout=15)
    except URLError as exc:
        print(f"health_down detail={type(exc).__name__}")
        return 2
    if code != 200 or not isinstance(body, dict) or not body.get("ready"):
        print(f"health_failed status={code}")
        return 2

    failed = False
    for label, fn in (("tier_a", lambda: _tier_a(base)), ("tier_b", lambda: _tier_b(base))):
        try:
            fn()
        except SmokeFailure as exc:
            print(f"{label} fail detail={exc}")
            failed = True
        except URLError as exc:
            print(f"{label} fail detail={type(exc).__name__}")
            failed = True

    llm_key = (os.environ.get("SMOKE_LLM_KEY") or "").strip()
    if llm_key:
        provider = (os.environ.get("SMOKE_LLM_PROVIDER") or "groq").strip()
        model = (os.environ.get("SMOKE_LLM_MODEL") or "").strip() or None
        try:
            _tier_c(base, llm_key, provider, model)
        except SmokeFailure as exc:
            print(f"tier_c fail detail={exc}")
            failed = True
        except URLError as exc:
            print(f"tier_c fail detail={type(exc).__name__}")
            failed = True
    else:
        print("tier_c skip reason=no_visitor_llm_key")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
