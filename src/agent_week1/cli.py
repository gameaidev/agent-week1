"""Interactive REPL.

Kept separate from ``loop.py`` so the loop can be driven by a test harness or
an eval runner without a terminal attached.
"""

from __future__ import annotations

import os
import sys
from typing import Any

import anthropic
from anthropic.types import MessageParam

from .dispatch import WORKSPACE_ROOT, resolve_workspace_file
from .loop import AgentTurnError, Usage, run_turn
from .policy import new_session_nonce, policy_for

DEFAULT_MODEL = "claude-sonnet-5"
SCRIPT_PREVIEW_LINES = 40


def _preview_script(filepath: str) -> str:
    """Show what the script actually does.

    Approving by filename is approving code you have not read. ``bash_1.sh``
    could have been ``rm -rf`` and the prompt would have looked identical.
    """
    try:
        path = resolve_workspace_file(str(filepath))
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        return f"  <could not read script: {type(exc).__name__}: {exc}>"

    lines = text.splitlines()
    shown = lines[:SCRIPT_PREVIEW_LINES]
    body = "\n".join(f"  | {line}" for line in shown)
    if len(lines) > SCRIPT_PREVIEW_LINES:
        body += f"\n  | ... ({len(lines) - SCRIPT_PREVIEW_LINES} more lines)"
    return body


def confirm_tool_call(
    tool_name: str, tool_input: dict[str, Any], tainted: bool
) -> bool:
    policy = policy_for(tool_name)

    print(f"\n--- approval required: {tool_name} ---")

    if tainted:
        print(
            "  ! This turn has already read outside content (a file, a page, or\n"
            "  ! command output). The model's request may be influenced by it.\n"
            "  ! Check that this call is something YOU asked for."
        )

    if tool_name == "run_bash":
        print(f"  script: {tool_input.get('filepath')!r}")
        print(_preview_script(tool_input.get("filepath", "")))
        print("  Scripts run with your user's filesystem and network access.")
    elif tool_name == "http_get":
        print(f"  url: {tool_input.get('url')!r}")
        print("  This sends a request off this machine. Check the URL for")
        print("  anything that looks like smuggled data in the path or query.")
    else:
        for key, value in tool_input.items():
            print(f"  {key}: {value!r}")

    if policy.has_egress:
        print("  (this tool can move data off the machine)")

    try:
        answer = input("Allow? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer in {"y", "yes"}


def main() -> None:
    required = ("ANTHROPIC_API_KEY",)
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        print(
            f"Missing required environment variable(s): {', '.join(missing)}",
            file=sys.stderr,
        )
        raise SystemExit(1)

    model = os.getenv("AGENT_MODEL", DEFAULT_MODEL)
    base_url = os.getenv("ANTHROPIC_BASE_URL")

    client = anthropic.Anthropic(
        api_key=os.environ["ANTHROPIC_API_KEY"],
        **({"base_url": base_url} if base_url else {}),
    )

    nonce = new_session_nonce()
    conversation: list[MessageParam] = []
    session_usage = Usage()

    print("agent-week1")
    print(f"  model:     {model}")
    print(f"  endpoint:  {base_url or 'https://api.anthropic.com (default)'}")
    print(f"  workspace: {WORKSPACE_ROOT}")
    print("  type 'exit' to quit\n")

    while True:
        try:
            user_text = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if user_text.lower() in {"exit", "quit"}:
            break
        if not user_text:
            continue

        try:
            result = run_turn(
                client,
                user_text,
                conversation,
                model=model,
                nonce=nonce,
                confirmer=confirm_tool_call,
            )
        except anthropic.APIError as exc:
            print(f"Request failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        except AgentTurnError as exc:
            print(f"Turn discarded: {exc}", file=sys.stderr)
            continue

        session_usage.merge(result.usage)
        print(f"\n{result.text}\n")
        print(
            f"  [turn: {result.rounds} round(s), {result.usage}]"
            f"\n  [session: {session_usage}]\n"
        )

    print(f"Session totals: {session_usage}")
