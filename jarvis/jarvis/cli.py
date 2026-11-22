"""Text client for trying Jarvis from a terminal: ``python -m jarvis.cli``.

Reads JARVIS_URL (default http://127.0.0.1:8200), JARVIS_CLI_TOKEN and
JARVIS_CLI_USER from the environment or the Jarvis env file. One-shot:
``python -m jarvis.cli "is the garage open?"``; no argument starts a prompt.
"""

from __future__ import annotations

import os
import sys

import httpx

from .config import DEFAULT_ENV_FILE


def main() -> int:
    from dotenv import load_dotenv

    load_dotenv(os.environ.get("JARVIS_ENV_FILE", DEFAULT_ENV_FILE), override=False)
    url = os.environ.get("JARVIS_URL", "http://127.0.0.1:8200").rstrip("/")
    token = os.environ.get("JARVIS_CLI_TOKEN", "")
    user = os.environ.get("JARVIS_CLI_USER", "")
    if not token or not user:
        print(
            "set JARVIS_CLI_TOKEN and JARVIS_CLI_USER (env or jarvis.env)",
            file=sys.stderr,
        )
        return 2
    headers = {"Authorization": f"Bearer {token}", "X-Jarvis-User": user}

    def ask(text: str) -> None:
        resp = httpx.post(
            f"{url}/v1/turn", json={"text": text}, headers=headers, timeout=120
        )
        if resp.status_code != 200:
            print(f"[{resp.status_code}] {resp.text}")
            return
        out = resp.json()
        tag = "" if out["speak"] else " (screen only)"
        tools = f"  [{', '.join(out['tools_used'])}]" if out["tools_used"] else ""
        print(f"{out['text']}{tag}{tools}  ({out['latency_ms']} ms)")

    one_shot = " ".join(sys.argv[1:]).strip()
    if one_shot:
        ask(one_shot)
        return 0
    try:
        while True:
            text = input("you> ").strip()
            if text:
                ask(text)
    except (EOFError, KeyboardInterrupt):
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
