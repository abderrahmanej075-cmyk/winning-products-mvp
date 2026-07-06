"""CJ Dropshipping — safe access token refresh.

Reads CJ_REFRESH_TOKEN from backend/.env.
Calls POST /v1/authentication/refreshAccessToken.
Writes new CJ_API_TOKEN (and CJ_REFRESH_TOKEN if rotated) to backend/.env.
Writes expiry timestamps CJ_TOKEN_EXPIRES_AT and CJ_REFRESH_TOKEN_EXPIRES_AT.

NEVER prints token values. Prints only booleans and ISO timestamps.

Usage (from project root or backend/ directory):
    python -m dotenv -f backend/.env run -- python backend/scripts/refresh_cj_token.py
or from backend/ directory:
    python -m dotenv -f .env run -- python scripts/refresh_cj_token.py
"""
import os
import re
import sys
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

# ------------------------------------------------------------------ locate .env

_SCRIPT_DIR = Path(__file__).resolve().parent          # backend/scripts/
_BACKEND_DIR = _SCRIPT_DIR.parent                      # backend/
_ENV_FILE = _BACKEND_DIR / ".env"

BASE_URL = os.getenv("CJ_API_BASE_URL", "https://developers.cjdropshipping.com/api2.0").rstrip("/")
REFRESH_TOKEN = os.getenv("CJ_REFRESH_TOKEN", "").strip()
ACCESS_TOKEN_TTL_DAYS = 180
REFRESH_TOKEN_TTL_DAYS = 180


def _read_env_lines():
    if not _ENV_FILE.exists():
        return []
    return _ENV_FILE.read_text(encoding="utf-8").splitlines(keepends=True)


def _set_env_key(lines: list, key: str, value: str) -> list:
    """Set or add a key=value line in-place. Never prints the value."""
    pattern = re.compile(rf"^{re.escape(key)}\s*=")
    for i, line in enumerate(lines):
        if pattern.match(line):
            lines[i] = f"{key}={value}\n"
            return lines
    lines.append(f"{key}={value}\n")
    return lines


def _write_env(lines: list) -> None:
    _ENV_FILE.write_text("".join(lines), encoding="utf-8")


def main():
    if not REFRESH_TOKEN:
        print("token_refresh_status=refresh_token_missing")
        print("action_required: set CJ_REFRESH_TOKEN in backend/.env")
        print("how_to_get: run backend/scripts/get_cj_tokens_from_api_key.py to capture tokens from your API Key")
        sys.exit(1)

    print(f"refresh_token_present=true")
    print(f"endpoint={BASE_URL}/v1/authentication/refreshAccessToken")

    try:
        resp = httpx.post(
            f"{BASE_URL}/v1/authentication/refreshAccessToken",
            json={"refreshToken": REFRESH_TOKEN},
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
        sys.exit(1)

    data = body.get("data") or {}
    new_access_token = data.get("accessToken", "").strip()
    new_refresh_token = data.get("refreshToken", "").strip()

    if not new_access_token:
        print("access_token_in_response=false")
        sys.exit(1)

    now = datetime.now(timezone.utc)
    access_expires = (now + timedelta(days=ACCESS_TOKEN_TTL_DAYS)).isoformat()
    refresh_expires = (now + timedelta(days=REFRESH_TOKEN_TTL_DAYS)).isoformat()

    lines = _read_env_lines()
    lines = _set_env_key(lines, "CJ_API_TOKEN", new_access_token)
    lines = _set_env_key(lines, "CJ_TOKEN_EXPIRES_AT", access_expires)

    refresh_token_updated = False
    if new_refresh_token and new_refresh_token != REFRESH_TOKEN:
        lines = _set_env_key(lines, "CJ_REFRESH_TOKEN", new_refresh_token)
        lines = _set_env_key(lines, "CJ_REFRESH_TOKEN_EXPIRES_AT", refresh_expires)
        refresh_token_updated = True
    else:
        lines = _set_env_key(lines, "CJ_REFRESH_TOKEN_EXPIRES_AT", refresh_expires)

    _write_env(lines)

    print(f"access_token_updated=true")
    print(f"refresh_token_updated={str(refresh_token_updated).lower()}")
    print(f"token_expires_at={access_expires}")
    print(f"refresh_token_expires_at={refresh_expires}")
    print("next_step: restart the backend to load the new CJ_API_TOKEN")


if __name__ == "__main__":
    main()
