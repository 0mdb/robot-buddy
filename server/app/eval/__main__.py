"""CLI runner for the BFCL-style tool-selection eval.

Usage:
    python -m app.eval [--host URL] [--threshold 0.85] [--output PATH]

Hits POST /eval/select_tool on the running planner server for each
scenario in app.eval.harness.SCENARIOS, scores the responses, and prints
a markdown report. Exits non-zero when the pass rate falls below the
gate threshold (default 0.85) so CI / `just eval-tools` can treat it
as a hard check.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import httpx

from app.eval.harness import format_report, run_scenarios


async def _generate_via_server(
    client: httpx.AsyncClient, base_url: str, system_prompt: str, user_text: str
) -> str:
    # system_prompt is unused on the wire — the server builds its own from
    # the same module we import. We accept it to satisfy the GenerateFn
    # signature and to keep the option open for passing it explicitly if we
    # ever want eval-side prompt overrides.
    del system_prompt
    resp = await client.post(
        f"{base_url.rstrip('/')}/eval/select_tool",
        json={"user_text": user_text},
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json().get("raw", "")


async def _run(base_url: str, threshold: float, output_path: Path | None) -> int:
    async with httpx.AsyncClient() as client:

        async def generate(system_prompt: str, user_text: str) -> str:
            return await _generate_via_server(
                client, base_url, system_prompt, user_text
            )

        report = await run_scenarios(generate)

    rendered = format_report(report, gate_threshold=threshold)
    print(rendered)

    if output_path is not None:
        output_path.write_text(rendered + "\n")

    return 0 if report.pass_rate >= threshold else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--host",
        default="http://127.0.0.1:8100",
        help="Planner server base URL (default: http://127.0.0.1:8100)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.85,
        help="Gate pass-rate threshold [0.0-1.0] (default: 0.85)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write the markdown report to.",
    )
    args = parser.parse_args()

    return asyncio.run(_run(args.host, args.threshold, args.output))


if __name__ == "__main__":
    sys.exit(main())
