"""Which credentials the agent will run on, for the web UI's "how am I signed in" badge.

Order the agent actually uses (and so the order we report):
  1. an API key the user typed into the UI (this browser session only, never written to disk)
  2. ANTHROPIC_API_KEY from the environment or the repo .env
  3. the local Claude Code login (subscription)

Claude Code login is only offered when the web server runs on your own machine (it binds to
127.0.0.1). Anthropic doesn't allow third-party products to offer claude.ai login or plan limits
to other people, so a hosted deployment must run key-only (`TRAVEL_WEB_KEY_ONLY=1`): then every
visitor brings their own API key and the server's login is never used.

Detection is a best guess from files on disk; it can't prove the login still works. An expired
login shows up on the first message, and the UI then offers the API-key option.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path

KEY_RE = re.compile(r"^sk-ant-[A-Za-z0-9_\-]{20,}$")


@dataclass
class AuthStatus:
    mode: str  # "browser_key" | "server_key" | "claude_login" | "none"
    label: str
    needs_key: bool = False
    reason: str | None = None  # e.g. "login_expired", "key_only", "key_rejected"

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


def looks_like_api_key(key: str) -> bool:
    return bool(KEY_RE.match(key.strip()))


def _mac_keychain_has_login() -> bool:
    try:
        r = subprocess.run(["security", "find-generic-password", "-s", "Claude Code-credentials"],
                           capture_output=True, timeout=3)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def claude_login_present(env: Mapping[str, str] | None = None, home: Path | None = None,
                         platform: str = sys.platform) -> bool:
    """True if Claude Code has a stored login (or an OAuth token in the environment)."""
    env = os.environ if env is None else env
    if env.get("CLAUDE_CODE_OAUTH_TOKEN"):
        return True
    config_dir = Path(env["CLAUDE_CONFIG_DIR"]) if env.get("CLAUDE_CONFIG_DIR") else (home or Path.home()) / ".claude"
    if (config_dir / ".credentials.json").is_file():
        return True
    return platform == "darwin" and _mac_keychain_has_login()


def detect(server_env: Mapping[str, str], browser_key: str | None = None, key_only: bool = False,
           login_present: bool | None = None, reason: str | None = None) -> AuthStatus:
    if browser_key:
        return AuthStatus("browser_key", "Your API key (this browser session)")
    if server_env.get("ANTHROPIC_API_KEY"):
        return AuthStatus("server_key", "API key from the server's .env")
    if key_only:
        return AuthStatus("none", "Enter your Anthropic API key to start", needs_key=True, reason=reason or "key_only")
    if reason == "login_expired":
        return AuthStatus("none", "Your Claude login has expired", needs_key=True, reason=reason)
    if login_present if login_present is not None else claude_login_present():
        return AuthStatus("claude_login", "Your Claude login (subscription)")
    return AuthStatus("none", "No Claude login found on this computer", needs_key=True, reason=reason or "no_login")


def is_api_key_rejected(error: str | None) -> bool:
    e = (error or "").lower()
    return any(s in e for s in ("invalid x-api-key", "invalid api key", "authentication_error"))
