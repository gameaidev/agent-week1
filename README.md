# agent-week1

A small command-line AI agent built with Python and the Anthropic SDK. It uses
a hand-written, bounded tool loop so the request, tool call, tool result, and
response flow remain easy to inspect.

The agent maintains conversation history and can ask the model to read project
files, run approved Bash scripts, or retrieve approved public HTTPS resources.
Its main focus is preserving valid tool history and keeping untrusted tool
output behind an explicit trust boundary.

## Requirements

- Python 3.12 or newer
- [`uv`](https://docs.astral.sh/uv/)
- An Anthropic API key, or a key for an Anthropic-compatible endpoint

The default model is `claude-sonnet-5`. Set `AGENT_MODEL` to use another model.

## Setup

Install the project dependencies:

```bash
uv sync
```

For the default Anthropic endpoint, set the API key:

```bash
export ANTHROPIC_API_KEY="your-anthropic-api-key"
```

To use an Anthropic-compatible provider, also set its base URL and model:

```bash
export ANTHROPIC_BASE_URL="https://provider.example/anthropic"
export AGENT_MODEL="provider-model-name"
export ANTHROPIC_API_KEY="your-provider-api-key"
```

`ANTHROPIC_API_KEY` is required. `ANTHROPIC_BASE_URL` and `AGENT_MODEL` are
optional; the CLI reports its selected endpoint and model at startup without
displaying credentials.

## Run

Start the interactive agent:

```bash
uv run agent-week1
```

Enter a prompt at the `You:` prompt. Enter `exit` or `quit`, or press Ctrl-C or
Ctrl-D, to stop the program.

The CLI reports API calls and input, output, cache-read, and cache-write tokens
for each turn and for the full session.

## Tools and approval policy

All tool results are treated as untrusted data. Successful results are wrapped
in a per-session, nonce-delimited fence before being returned to the model. If
a turn has consumed tool output, later approval prompts warn that the requested
action may be influenced by outside content.

### `read_file`

Reads a UTF-8 text file inside the configured workspace.

- Relative paths are resolved from the workspace root.
- Absolute paths and symlinks must still resolve inside the workspace.
- Directories and other non-regular files are rejected.
- Files are limited to 1 MB.
- Reading does not require confirmation.

### `run_bash`

Runs an existing Bash script located inside the workspace.

- Every execution requires explicit console confirmation.
- The approval prompt previews up to the first 40 lines of the script.
- A script is limited to 30 seconds.
- Captured output returned to the model is limited to 100 KB.
- Environment variables whose names appear to contain credentials are removed
  from the child process environment.
- Exit failures and timeouts are returned to the model as tool errors.

Approved scripts are not sandboxed. They can read files, access the network,
and modify the system with the permissions of the current user. Review the
preview before approving a call.

### `http_get`

Retrieves text from a public HTTPS URL.

- Every request requires explicit console confirmation and displays the URL.
- Only HTTPS is accepted.
- Embedded URL credentials and non-public IP addresses are rejected.
- Redirect destinations are validated again.
- Responses are limited to supported text-based content types and 2 MB.
- Requests have a 10-second timeout.

The URL validation reduces SSRF risk but does not eliminate DNS-rebinding risk;
the hostname is validated before `urllib` performs its own connection-time
resolution.

## How it works

For each console prompt, the agent:

1. Copies the existing conversation and trims only at complete turn boundaries.
2. Adds the user's text and calls the configured model with strict tool schemas.
3. Normalizes SDK content blocks into JSON-serializable dictionaries.
4. Checks each tool against a centralized policy, obtains any required
   confirmation, executes it, and fences successful untrusted output.
5. Returns tool results to the model and repeats until the model finishes or
   the eight-round limit is reached.
6. Commits the working history only when it is safe to preserve.

Tool exceptions become error results so the model can recover. A refusal or a
response truncated while emitting a tool call discards the incomplete turn,
preventing an unpaired `tool_use` block from corrupting later requests. Valid
text-only truncation is preserved and clearly marked.

Conversation history is capped by `MAX_HISTORY_MESSAGES`, but an oversized
single turn is kept whole rather than splitting a `tool_use`/`tool_result`
pair. A user turn is capped by `MAX_TOOL_ROUNDS` model calls.

See [docs/agent-architecture.md](docs/agent-architecture.md) for the component
and trust-boundary diagram.

## Workspace configuration

By default, file tools discover the repository root using `pyproject.toml` or
`.git`. Set `AGENT_WORKSPACE_ROOT` before starting the program to use another
existing directory:

```bash
export AGENT_WORKSPACE_ROOT="/absolute/path/to/workspace"
```

## Tests

Run the current pure-logic test suite with an ephemeral pytest dependency:

```bash
uv run --with pytest pytest src/agent_week1/test_agent_week1.py -v
```

The nine tests cover untrusted-data fencing, nonce generation, conservative
defaults for unknown tools, approval policy, turn-boundary detection and
trimming, and JSON-safe SDK block normalization.

## Project structure

```text
src/agent_week1/__init__.py            Public package exports
src/agent_week1/cli.py                 Interactive REPL, approvals, and metrics
src/agent_week1/loop.py                Bounded model/tool loop
src/agent_week1/history.py             Block normalization and safe trimming
src/agent_week1/policy.py              Tool policy and untrusted-data fencing
src/agent_week1/dispatch.py            Tool handlers and safety checks
src/agent_week1/tools_def.py           Model-facing tool schemas
src/agent_week1/test_agent_week1.py    Pure-logic tests
docs/agent-architecture.md             Architecture and trust-boundary diagram
```
