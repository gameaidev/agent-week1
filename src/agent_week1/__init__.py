"""agent-week1: a hand-written Anthropic tool-use loop.

``__init__.py`` holds re-exports only. Logic lives in modules so it can be
imported without side effects and driven by a test harness.

Layout:
    policy.py    trust policy + untrusted-data fencing + system prompt
    tools_def.py tool schemas
    dispatch.py  tool handlers
    history.py   normalisation + turn-aware trimming
    loop.py      the agent loop
    cli.py       REPL
"""

from .cli import main
from .loop import AgentTurnError, TurnResult, Usage, run_turn
from .policy import build_system_prompt, fence, new_session_nonce, policy_for

__all__ = [
    "main",
    "run_turn",
    "TurnResult",
    "Usage",
    "AgentTurnError",
    "new_session_nonce",
    "fence",
    "build_system_prompt",
    "policy_for",
]
