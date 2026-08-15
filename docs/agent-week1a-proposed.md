Tests pass (9/9), and I replayed your exact injection scenario against a stub client: `read_file` output comes back fenced, the taint flag is set, and `run_bash` hits the gate with the escalated warning.

**First, a correction.** I flagged the `#!/bin/zsh` shebang as a portability risk. Wrong — `run_bash` invokes `["bash", "--", str(path)]`, so the shebang is never consulted. Your dispatch was already correct there. The SSRF guard is also better than I expected: DNS resolution with `ip.is_global`, redirect re-validation, and a post-fetch `geturl()` check is the right shape. Its one remaining gap is DNS rebinding — you validate the resolved IPs, then urllib resolves independently — which I've documented in the docstring rather than fixed, since fixing it means pinning the IP and preserving the Host header.

**What changed:**

`policy.py` is new and is the load-bearing piece. One table answers "does this return untrusted content," "does it need approval," "does it have egress." Unknown tools default to maximally dangerous. The fence uses a per-session random nonce plus literal neutralisation, because a fixed delimiter is forgeable by the payload itself.

The loop now tracks **taint**: once any tool returns outside content in a turn, later confirmations carry an explicit warning that the model's request may be downstream of attacker-controlled data. That's a coarse stand-in for real taint propagation, but it catches the `read_file` → `http_get` exfiltration shape specifically.

`stop_reason` handling is split properly. `max_tokens` with a `tool_use` block present raises and **discards the turn without committing** — that's the poisoning bug. Text-only truncation still commits, since the content is valid. `refusal` discards. History mutation happens only on success.

Trimming walks backward to turn boundaries. There's a test that asserts the old `del messages[:2]` produces invalid history, so you can see the failure concretely.

`run_bash` approval now prints the script body. Approving by filename was approving code you hadn't read.

Tool descriptions now carry their constraints inline — size caps, scheme restrictions, "this returns raw HTML markup, not rendered text." Every constraint stated up front is a round trip the model doesn't waste failing and retrying.

**Two things to sit with.** The tests assert history *validity*, not model behaviour — that split is exactly the week 1 / week 2 boundary. And every turn now prints its token usage, which is the data you need for the concurrency-cost question from earlier.

**The honest limit:** the fence is a mitigation, not a fix. A sufficiently persuasive injection can still talk the model past it. The gate on side-effecting tools is the actual control; the fence just reduces how often you're asked. For the digital human, where input is untrusted speech from strangers and nobody is at a terminal to type `y`, you'll need the slow path's side-effecting tools gated by something other than a human — an allowlist of pre-approved actions, most likely. Worth designing before you get there.