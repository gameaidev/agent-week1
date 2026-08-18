"""The agent loop.

Control flow is driven entirely by ``stop_reason``. The important property is
that the *model*, not this code, decides when the loop ends -- which is what
makes this an agent rather than a workflow, and is also the reason
``MAX_TOOL_ROUNDS`` exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from anthropic import Anthropic
from anthropic.types import MessageParam, ToolResultBlockParam

from .dispatch import DISPATCH
from .history import normalise_blocks, trim_to_turn_boundary
from .policy import build_system_prompt, fence, policy_for
from .tools_def import TOOLS

MAX_TOOL_ROUNDS = 8
MAX_HISTORY_MESSAGES = 100


class AgentTurnError(RuntimeError):
    """The turn could not complete and was NOT committed to history.

    Raised for any condition that would leave an unpaired ``tool_use`` block
    in the transcript. Committing one poisons every subsequent request in the
    session with a 400, so the turn is discarded instead.
    """


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    api_calls: int = 0

    def add(self, usage: Any) -> None:
        self.api_calls += 1
        self.input_tokens += getattr(usage, "input_tokens", 0) or 0
        self.output_tokens += getattr(usage, "output_tokens", 0) or 0
        self.cache_read_tokens += (
            getattr(usage, "cache_read_input_tokens", 0) or 0
        )
        self.cache_write_tokens += (
            getattr(usage, "cache_creation_input_tokens", 0) or 0
        )

    def merge(self, other: "Usage") -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_read_tokens += other.cache_read_tokens
        self.cache_write_tokens += other.cache_write_tokens
        self.api_calls += other.api_calls

    def __str__(self) -> str:
        return (
            f"{self.api_calls} call(s), "
            f"in={self.input_tokens:,} out={self.output_tokens:,} "
            f"cache_r={self.cache_read_tokens:,} cache_w={self.cache_write_tokens:,}"
        )


@dataclass
class TurnResult:
    text: str
    rounds: int
    usage: Usage = field(default_factory=Usage)
    hit_round_limit: bool = False
    truncated: bool = False


# A confirmer takes (tool_name, tool_input, tainted) and returns approval.
Confirmer = Callable[[str, dict[str, Any], bool], bool]


def _always_deny(tool_name: str, tool_input: dict[str, Any], tainted: bool) -> bool:
    return False


def run_turn(
    client: Anthropic,
    user_text: str,
    conversation: list[MessageParam],
    *,
    model: str,
    nonce: str,
    confirmer: Confirmer = _always_deny,
) -> TurnResult:
    """Run one user turn to completion.

    ``conversation`` is mutated in place only on success. On failure it is
    left exactly as it was, so a poisoned or partial turn cannot corrupt the
    session.
    """
    working: list[MessageParam] = trim_to_turn_boundary(
        list(conversation), MAX_HISTORY_MESSAGES
    )
    working.append({"role": "user", "content": user_text})

    system_prompt = build_system_prompt(nonce)
    usage = Usage()

    # Taint tracking: once any tool has returned outside content in this turn,
    # every later side-effecting call is suspect, because the model's reasoning
    # is now downstream of data an attacker may control. This is a coarse
    # stand-in for real per-value taint propagation, but it catches the
    # read_file -> http_get exfiltration shape.
    tainted = False

    for round_index in range(MAX_TOOL_ROUNDS):
        resp = client.messages.create(
            model=model,
            max_tokens=4096,
            tools=TOOLS,
            system=system_prompt,
            messages=working,
        )
        usage.add(resp.usage)

        blocks = normalise_blocks(resp.content)
        has_tool_use = any(b.get("type") == "tool_use" for b in blocks)

        # ---- stop_reason dispatch -------------------------------------
        # The loop exits on anything other than "tool_use", but the exits are
        # not interchangeable. Collapsing them into `!= "tool_use"` is what
        # lets a truncated tool_use block into the transcript.

        if resp.stop_reason == "max_tokens":
            if has_tool_use:
                # The tool_use block may be cut mid-JSON. Nothing here is
                # safe to keep.
                raise AgentTurnError(
                    "Response hit max_tokens while emitting a tool call. "
                    "Turn discarded; retry with a higher max_tokens."
                )
            # Text-only truncation is recoverable: the content is valid, just
            # incomplete.
            text = _text_of(blocks)
            working.append({"role": "assistant", "content": blocks})
            conversation[:] = working
            return TurnResult(
                text=text + "\n\n[response truncated at max_tokens]",
                rounds=round_index + 1,
                usage=usage,
                truncated=True,
            )

        if resp.stop_reason == "refusal":
            raise AgentTurnError(
                "Model declined to continue (stop_reason=refusal). "
                "Turn discarded."
            )

        working.append({"role": "assistant", "content": blocks})

        if resp.stop_reason != "tool_use":
            # end_turn, stop_sequence, or anything new the API introduces.
            conversation[:] = working
            return TurnResult(
                text=_text_of(blocks), rounds=round_index + 1, usage=usage
            )

        if not has_tool_use:
            raise AgentTurnError(
                "stop_reason was tool_use but no tool_use block was present."
            )

        # ---- execute tools --------------------------------------------
        results: list[ToolResultBlockParam] = []
        for block in blocks:
            if block.get("type") != "tool_use":
                continue

            name = block["name"]
            tool_input = dict(block.get("input") or {})
            policy = policy_for(name)
            handler = DISPATCH.get(name)

            output: str
            is_error = False

            if handler is None:
                output = (
                    f"Unknown tool: {name}. Available tools: "
                    f"{', '.join(sorted(DISPATCH))}."
                )
                is_error = True
            elif policy.requires_confirmation and not confirmer(
                name, tool_input, tainted
            ):
                output = f"The user denied execution of {name}."
                is_error = True
            else:
                if policy.takes_approval_kwarg:
                    tool_input["approved"] = True
                try:
                    output = str(handler(**tool_input))
                except Exception as exc:  # noqa: BLE001
                    # Tool failures are returned to the model, not raised.
                    # This is what lets it self-correct -- a wrong path or a
                    # bad URL becomes feedback instead of a crash.
                    output = f"Tool execution failed: {type(exc).__name__}: {exc}"
                    is_error = True

            if policy.returns_untrusted and not is_error:
                output = fence(nonce, name, output)
                tainted = True

            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": output,
                    "is_error": is_error,
                }
            )

        working.append({"role": "user", "content": results})

    # ---- round limit --------------------------------------------------
    # Commit the history so far so the user can continue, but make the stop
    # visible: silent truncation of an agent's plan is worse than a loud one.
    conversation[:] = working
    return TurnResult(
        text=(
            f"Stopped after {MAX_TOOL_ROUNDS} tool rounds without a final answer. "
            "The task may be too broad, or the agent may be looping. "
            "Narrow the request and try again."
        ),
        rounds=MAX_TOOL_ROUNDS,
        usage=usage,
        hit_round_limit=True,
    )


def _text_of(blocks: list[dict[str, Any]]) -> str:
    return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
