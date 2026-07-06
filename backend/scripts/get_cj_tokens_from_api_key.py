"""CJ Dropshipping — first-time token capture from API Key.

Key resolution order:
  1. Environment variable CJ_API_KEY_TEMP (any OS)
  2. Windows clipboard via PowerShell Get-Clipboard (Windows only, if CJ_API_KEY_TEMP absent)

Calls POST /v1/authentication/getAccessToken.
Writes CJ_API_TOKEN, CJ_REFRESH_TOKEN, CJ_TOKEN_EXPIRES_AT,
CJ_REFRESH_TOKEN_EXPIRES_AT into backend/.env.

NEVER prints token or key values. Prints only safe booleans and timestamps.

Usage (from backend/ directory):
    # Option A — env var (any OS):
    $env:CJ_API_KEY_TEMP="<your_api_key>"
    python scripts/get_cj_tokens_from_api_key.py

    # Option B — Windows clipboard (copy API Key first, then):
    python scripts/get_cj_tokens_from_api_key.py

    # Check availability without making API call:
    python scripts/get_cj_tokens_from_api_key.py --check

SECURITY:
    - Never paste your API Key into chat with an AI assistant.
    - Never commit backend/.env to git.
    - CJ_API_KEY_TEMP is NOT written to .env — only tokens are saved.
    - getAccessToken within 24h returns the same cached token (CJ caches it).
"""
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

_SCRIPT_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _SCRIPT_DIR.parent
_ENV_FILE = _BACKEND_DIR / ".env"

BASE_URL = os.getenv("CJ_API_BASE_URL", "https://developers.cjdropshipping.com/api2.0").rstrip("/")
ACCESS_TOKEN_TTL_DAYS = 180
REFRESH_TOKEN_TTL_DAYS = 180


# ------------------------------------------------------------------ key resolution

def _key_from_clipboard() -> str:
    """Read text from Windows clipboard via PowerShell. Returns empty string on any failure."""
    if sys.platform != "win32":
        return ""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", "Get-Clipboard"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return (result.stdout or "").strip()
    except Exception:
        return ""


def _resolve_api_key() -> tuple[str, str]:
    """Return (api_key, source) without printing the key value.

    source is one of: 'env', 'clipboard', 'not_found'
    """
    key = os.getenv("CJ_API_KEY_TEMP", "").strip()
    if key:
        return key, "env"
    if sys.platform == "win32":
        key = _key_from_clipboard()
        if key:
            return key, "clipboard"
    return "", "not_found"


# ------------------------------------------------------------------ .env helpers

def _read_env_lines() -> list:
    if not _ENV_FILE.exists():
        return []
    return _ENV_FILE.read_text(encoding="utf-8").splitlines(keepends=True)


def _set_env_key(lines: list, key: str, value: str) -> list:
    pattern = re.compile(rf"^{re.escape(key)}\s*=")
    for i, line in enumerate(lines):
        if pattern.match(line):
            lines[i] = f"{key}={value}\n"
            return lines
    lines.append(f"{key}={value}\n")
    return lines


def _write_env(lines: list) -> None:
    _ENV_FILE.write_text("".join(lines), encoding="utf-8")


# ------------------------------------------------------------------ main

def main():
    check_only = "--check" in sys.argv

    api_key, source = _resolve_api_key()
    key_found = bool(api_key)

    print(f"api_key_seen={str(key_found).lower()}")

    if not key_found:
        print("token_capture_ready=false")
        print("reason=api_key_not_in_env_or_clipboard")
        if sys.platform == "win32":
            print("hint: copy your CJ API Key to clipboard, then re-run this script")
        else:
            print("hint: set CJ_API_KEY_TEMP=<your_api_key> then re-run this script")
        sys.exit(1)

    if check_only:
        print("token_capture_ready=true")
        print(f"key_source={source}")
        print("run without --check to proceed with token capture")
        sys.exit(0)

    print(f"token_capture_ready=true")
    print(f"key_source={source}")
    print(f"endpoint={BASE_URL}/v1/authentication/getAccessToken")

    try:
        resp = httpx.post(
            f"{BASE_URL}/v1/authentication/getAccessToken",
            json={"apiKey": api_key},
            timeout=15,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        print(f"http_error={e.response.status_code}")
        sys.exit(1)
    except Exception as e:
        print(f"request_error={type(e).__name__}")
        sys.exit(1)

    body = resp.json()
    if not body.get("result"):
        print(f"api_error=true  message={body.get('message', 'unknown')}")
        print("note: CJ caches tokens — repeated calls within 24h return the same token")
        sys.exit(1)

    data = body.get("data") or {}
    access_token = data.get("accessToken", "").strip()
    refresh_token = data.get("refreshToken", "").strip()

    if not access_token:
        print("access_token_in_response=false")
        sys.exit(1)

    now = datetime.now(timezone.utc)
    access_expires = (now + timedelta(days=ACCESS_TOKEN_TTL_DAYS)).isoformat()
    refresh_expires = (now + timedelta(days=REFRESH_TOKEN_TTL_DAYS)).isoformat()

    lines = _read_env_lines()
    lines = _set_env_key(lines, "CJ_API_TOKEN", access_token)
    lines = _set_env_key(lines, "CJ_TOKEN_EXPIRES_AT", access_expires)

    refresh_saved = False
    if refresh_token:
        lines = _set_env_key(lines, "CJ_REFRESH_TOKEN", refresh_token)
        lines = _set_env_key(lines, "CJ_REFRESH_TOKEN_EXPIRES_AT", refresh_expires)
        refresh_saved = True

    _write_env(lines)

    print(f"access_token_saved=true")
    print(f"refresh_token_saved={str(refresh_saved).lower()}")
    print(f"token_expires_at={access_expires}")
    if refresh_saved:
        print(f"refresh_token_expires_at={refresh_expires}")
    print("next_step: restart backend with: python -m dotenv -f .env run -- python -m uvicorn main:app --host 0.0.0.0 --port 8000")


if __name__ == "__main__":
    main()
