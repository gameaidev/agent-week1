# Objective:
~200 lines, three tools (`read_file, run_bash, http_get`), a while loop, no framework. Give it a task in a scratch git repo. Watch it fail.

# Env Setup
1. Installed `uv` with Python 3.12
2. Created a folder `~/source/agent-week1`
2. Ran `uv init --package --python 3.12`
3. Created, committed, and pushed the repo to `github`
4. 

# Design
Execute a task based on a user's task goal.

The task is to find vulnerability in the existing `parsercppapp` C++ app (about 6 source files).

## Data structure
messages: contain input data to LLM

tools = [`read_file, run_bash, http_get`]

stop_reason: found_issue == true

## Algorithm

```python
found_issue = false

while (found_issue != true) {

  client.messages.create()

  read_file:
  > 1. Read a .h and .cpp source file from the source file list.
  > 2. Construct `message` for LLM input.

  run_bash:
  > Run a bash script to execute Python script to prepare input to LLM.

  http_get:
  > 1. Call LLM API.
  > 2. Get reply from LLM call.
  > 3. Return result => (CWE found with description and assign found_issue=true) or "issue not found".

}

print out `result`
```