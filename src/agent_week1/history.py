"""Conversation history: normalisation and turn-aware trimming.

Two invariants the Anthropic API enforces, and that naive trimming breaks:

  1. Every ``tool_result`` block must reference a ``tool_use`` block in the
     immediately preceding assistant message.
  2. History cannot begin with a message whose content is ``tool_result``
     blocks, because there is no preceding assistant message to pair with.

``del messages[:2]`` violates both. It also does not actually bound the list,
because one turn with N tool rounds appends 2N messages, not 2.
"""

from __future__ import annotations

from typing import Any, Iterable

from anthropic.types import MessageParam


def normalise_blocks(blocks: Iterable[Any]) -> list[dict[str, Any]]:
    """Convert SDK content blocks to plain dicts.

    ``resp.content`` is a list of pydantic models. Appending them directly to
    ``messages`` round-trips fine through the SDK, but the moment you try to
    ``json.dumps`` the history -- for a trace exporter, a checkpoint, a test
    fixture -- it fails. Normalising at the boundary is cheaper than
    discovering this in week 2.

    ``exclude_none`` keeps optional-but-unset fields (e.g. ``citations``) out
    of the payload. Verify this against your own traffic if you start using
    extended thinking, where block shape matters more.
    """
    out: list[dict[str, Any]] = []
    for block in blocks:
        if isinstance(block, dict):
            out.append(block)
        else:
            out.append(block.model_dump(mode="json", exclude_none=True))
    return out


def is_turn_start(message: MessageParam) -> bool:
    """True if this user message opens a turn (i.e. is not tool results)."""
    if message.get("role") != "user":
        return False
    content = message.get("content")
    if isinstance(content, str):
        return True
    if not isinstance(content, list):
        return False
    return not any(
        isinstance(block, dict) and block.get("type") == "tool_result"
        for block in content
    )


def trim_to_turn_boundary(
    messages: list[MessageParam], max_messages: int
) -> list[MessageParam]:
    """Drop whole turns from the front until the history fits the budget.

    Never splits a ``tool_use`` / ``tool_result`` pair, and never leaves a
    tool-result message at index 0. If a single turn is larger than the
    budget, that turn is kept intact and returned oversized -- an oversized
    but valid history beats a compact invalid one.
    """
    if len(messages) <= max_messages:
        return messages

    starts = [i for i, m in enumerate(messages) if is_turn_start(m)]
    if not starts:
        return messages

    for start in starts:
        if len(messages) - start <= max_messages:
            return messages[start:]

    return messages[starts[-1] :]
