import os
import sys

import anthropic
from anthropic import Anthropic
from anthropic.types import MessageParam, ToolResultBlockParam

from .dispatch import DISPATCH
from .tools_def import TOOLS


MODEL = "deepseek-v4-flash"
MAX_TOOL_ROUNDS = 8
MAX_HISTORY_MESSAGES = 100
CONFIRMATION_REQUIRED = {"run_bash"}


def _confirm_tool_call(tool_name: str, tool_input: dict[str, object]) -> bool:
    if tool_name != "run_bash":
        return True

    filepath = tool_input.get("filepath")
    print(f"\nThe model requested Bash execution for {filepath!r}.")
    print("Approved scripts can read files, access the network, and modify your system.")
    try:
        answer = input("Allow this execution? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer in {"y", "yes"}


'''
This function trims the history of messages to ensure that it does not exceed the maximum allowed number of messages.
* -> None: modifies messages directly; it returns nothing.
* MAX_HISTORY_MESSAGES - 2: reserves two slots for the next user message and assistant response.
* del messages[:2]: deletes the two oldest messages.
* while: repeats until the history is small enough.
With MAX_HISTORY_MESSAGES = 100, a 104-message list is reduced like this:
  104 → 102 → 100 → 98
Important caveat: deleting two messages assumes history consists of simple user/assistant pairs. 
Tool calls can span linked tool_use and tool_result messages, so this could separate them and produce 
invalid history. It also doesn’t strictly enforce 100 messages when one turn performs multiple tool calls. 
A safer implementation should trim complete conversation turns while keeping tool calls and their results together.
'''
def _trim_history(messages: list[MessageParam]) -> None:
    while len(messages) > MAX_HISTORY_MESSAGES - 2:
        del messages[:2]


def event_loop(
    client: Anthropic,
    user_text: str,
    messages: list[MessageParam] | None = None,
) -> str:
    conversation = messages if messages is not None else []
    working_messages = list(conversation)
    _trim_history(working_messages)
    working_messages.append({"role": "user", "content": user_text})

    for _ in range(MAX_TOOL_ROUNDS):
        resp = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            tools=TOOLS,
            system="Your name is Serenity. You are a helpful assistant.",
            messages=working_messages,
        )
        working_messages.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason != "tool_use":
            response_text = "".join(
                block.text for block in resp.content if block.type == "text"
            )
            conversation[:] = working_messages
            return response_text

        results: list[ToolResultBlockParam] = []
        for block in resp.content:
            if block.type != "tool_use":
                continue

            handler = DISPATCH.get(block.name)
            is_error = False
            if handler is None:
                output = f"Unknown tool: {block.name}"
                is_error = True
            elif not _confirm_tool_call(block.name, block.input):
                output = f"User denied execution of tool: {block.name}"
                is_error = True
            else:
                try:
                    arguments = dict(block.input)
                    if block.name in CONFIRMATION_REQUIRED:
                        arguments["approved"] = True
                    output = handler(**arguments)
                except Exception as exc:
                    output = (
                        f"Tool execution failed: {type(exc).__name__}: {exc}"
                    )
                    is_error = True

            result: ToolResultBlockParam = {
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": str(output),
                "is_error": is_error
            }
            if is_error:
                result["is_error"] = True
            results.append(result)

        if not results:
            raise RuntimeError("Model stopped for tool use without requesting a tool.")
        working_messages.append({"role": "user", "content": results})

    limit_message = (
        f"Stopped after {MAX_TOOL_ROUNDS} consecutive tool rounds. "
        "Please refine your request before continuing."
    )
    working_messages.append({"role": "assistant", "content": limit_message})
    conversation[:] = working_messages
    return limit_message


def main() -> None:
    print("Hello from agent-week1!")

    required_environment = ("ANTHROPIC_BASE_URL", "ANTHROPIC_API_KEY")
    missing = [name for name in required_environment if not os.getenv(name)]
    if missing:
        print(
            f"Missing required environment variable(s): {', '.join(missing)}",
            file=sys.stderr,
        )
        return

    client = anthropic.Anthropic(
        base_url=os.environ["ANTHROPIC_BASE_URL"],
        api_key=os.environ["ANTHROPIC_API_KEY"],
    )
    messages: list[MessageParam] = []

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
            response_text = event_loop(client, user_text, messages)
        except anthropic.APIError as exc:
            print(f"Request failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        except RuntimeError as exc:
            print(f"Agent error: {exc}", file=sys.stderr)
            continue
        print(response_text)
