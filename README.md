# agent-week1

A small command-line AI agent built with Python and the Anthropic SDK. It uses
an Anthropic-compatible API endpoint, maintains conversation history, and can
ask the model to read project files, run approved Bash scripts, or retrieve
public HTTPS resources.

The project intentionally uses a simple tool-dispatch loop rather than an agent
framework so the request, tool call, tool result, and response flow remain easy
to inspect.

## Requirements

- Python 3.12 or newer
- [`uv`](https://docs.astral.sh/uv/)
- An Anthropic-compatible API endpoint and API key

The configured model is `deepseek-v4-flash`.

## Setup

Install the project dependencies:

```bash
uv sync
```

Configure the API connection:

```bash
export ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic"
export ANTHROPIC_API_KEY="your-deepseek-api-key"
```

Both variables are required. The CLI reports missing variables and exits
without displaying their values.

## Run

Start the interactive agent:

```bash
uv run agent-week1
```

Enter a prompt at the `You:` prompt. Enter `exit` or `quit`, or press Ctrl-C or
Ctrl-D, to stop the program.

The agent reuses recent conversation messages between prompts. Before a new
request, older messages are trimmed according to `MAX_HISTORY_MESSAGES`. A
single request is limited to `MAX_TOOL_ROUNDS` consecutive tool rounds.

## Tools

### `read_file`

Reads a UTF-8 text file inside the project workspace.

- Relative paths are resolved from the workspace root.
- Absolute paths and symlinks must still resolve inside the workspace.
- Files are limited to 1 MB.
- Directories and other non-regular files are rejected.

### `run_bash`

Runs a Bash script located inside the workspace.

- Every execution requires explicit confirmation at the console.
- A script is limited to 30 seconds.
- Captured output returned to the model is limited to 100 KB.
- Environment variables whose names appear to contain credentials are removed
  from the child process environment.
- Exit failures and timeouts are returned to the model as tool errors.

Approved scripts are not sandboxed. They can read files, access the network,
and modify the system with the permissions of the current user. Review the path
shown in the confirmation prompt before approving it.

### `http_get`

Retrieves text from a public HTTPS URL.

- Only HTTPS is accepted.
- Embedded URL credentials and non-public IP addresses are rejected.
- Redirect destinations are validated again.
- Responses are limited to supported text-based content types and 2 MB.
- Requests have a 10-second timeout.

## How it works

For each console prompt, the agent:

1. Adds the user's text to a working copy of the conversation history.
2. Calls the configured model with the available tool schemas.
3. Dispatches requested tools and returns their results to the model.
4. Repeats until the model produces a final response or reaches the tool-round
   limit.
5. Saves completed conversation history for the next console prompt.

Tool exceptions are converted into error results so the model can explain or
recover from failures. API and console-input errors are handled by the CLI.

## Workspace configuration

By default, file tools use the repository root as their workspace. Set
`AGENT_WORKSPACE_ROOT` before starting the program to use a different root:

```bash
export AGENT_WORKSPACE_ROOT="/absolute/path/to/workspace"
```

The directory should exist before the agent starts.

## Tests

Run the unit tests with:

```bash
uv run python -m unittest discover -s tests -v
```

The tests cover conversation reuse, tool-loop limits, strict tool schemas,
workspace path restrictions, Bash approval and output capture, and unsafe URL
rejection.

## Project structure

```text
src/agent_week1/__init__.py  Interactive CLI and model/tool loop
src/agent_week1/dispatch.py  Tool implementations and safety checks
src/agent_week1/tools_def.py Tool schemas sent to the model
tests/test_agent.py          Unit tests
```
