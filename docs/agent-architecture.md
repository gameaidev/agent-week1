# Agent architecture

Arrows point from each component to the dependency or service it invokes.
Dashed arrows represent returned data. Red nodes are untrusted data sources or
side-effecting runtimes.

```mermaid
flowchart LR
    User([User])

    subgraph App["agent_week1 application"]
        CLI["cli.py<br/>REPL, session state, approvals"]
        Conversation[("Conversation history")]

        subgraph Core["Agent core"]
            Loop["loop.py<br/>bounded model/tool loop"]
            History["history.py<br/>normalize blocks and trim whole turns"]
            Policy["policy.py<br/>tool policy, taint, fences, system prompt"]
            Schemas["tools_def.py<br/>strict model-facing tool schemas"]
        end

        subgraph ToolLayer["Tool execution layer"]
            Dispatch["dispatch.py<br/>handler registry and safety checks"]
            ReadFile["read_file<br/>contained path and 1 MB limit"]
            RunBash["run_bash<br/>approval, timeout, filtered environment"]
            HttpGet["http_get<br/>HTTPS and public-address validation"]
        end
    end

    subgraph External["External dependencies and trust boundary"]
        SDK["Anthropic Python SDK"]
        Model["Anthropic-compatible model API"]
        Workspace[("Workspace files")]
        Bash["Bash process"]
        Web["Public HTTPS resources"]
    end

    User -->|prompt| CLI
    CLI -->|owns| Conversation
    CLI -->|run_turn and confirmer callback| Loop
    CLI -->|approval and egress policy| Policy
    CLI -->|resolve script for preview| Dispatch
    Loop -->|trim and serialize safely| History
    Loop -->|read and commit completed turns| Conversation
    Loop -->|build prompt, check approval, fence output| Policy
    Loop -->|advertise available tools| Schemas
    Loop -->|messages.create with history and tool results| SDK
    SDK -.->|normalized model response| Loop
    SDK <-->|HTTPS| Model

    Loop -->|dispatch approved tool calls| Dispatch
    Dispatch --> ReadFile
    Dispatch --> RunBash
    Dispatch --> HttpGet

    ReadFile --> Workspace
    RunBash -->|load approved script| Workspace
    RunBash -->|execute| Bash
    HttpGet -->|validated request| Web

    Workspace -.->|untrusted file content| ReadFile
    Bash -.->|untrusted stdout and stderr| RunBash
    Web -.->|untrusted response body| HttpGet
    Dispatch -.->|result or is_error| Loop
    Policy -.->|nonce-delimited untrusted_data| Loop

    Loop -->|approval request and taint warning| CLI
    CLI -->|script preview or full URL| User
    User -.->|allow or deny| CLI
    Loop -.->|final text and usage| CLI
    CLI -.->|answer and metrics| User

    classDef boundary fill:#fff1f1,stroke:#c62828,color:#5f1010;
    classDef safety fill:#eef7ff,stroke:#1565c0,color:#0d3f75;
    classDef core fill:#f4f0ff,stroke:#6542a6,color:#35205c;
    class Workspace,Bash,Web boundary;
    class History,Policy,Dispatch safety;
    class Loop,Schemas core;
```
