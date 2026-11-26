# Stats for nerds: performance metrics

Every number in Stats for nerds is one of three kinds, and the UI shows which:

| Kind | Shown as | Meaning |
| --- | --- | --- |
| **Exact** | `412 tok/s` | Counted or timed directly from the provider stream or its own usage report. |
| **Estimated** | `≈412 tok/s` | Derived: characters converted to tokens, or an exact total spread over measured time. The tooltip says how. |
| **Unavailable** | `—` | The provider does not expose it. The tooltip names the provider. Never a guess. |

All times are taken on the T3 server, where the adapter reads the provider's
stream, with a monotonic clock. They therefore include the provider's network
latency, not the UI's rendering latency.

## Turn timeline

```
request sent ──► first generated token ──► first answer text ──► … ──► turn ends
     │                 (TTFT)                    (TTFA)                (turn duration)
     └── tool execution windows are excluded from generation time ──┘
```

### TTFT — time to first token

From the moment the adapter hands the request to the provider (Claude: the user
message is written to the SDK query; Codex: `turn/start` is sent; ACP:
`session/prompt` is sent) to the **first generated token** of the turn.

A generated token is a streamed reasoning token, answer text, or tool-call
argument text the model writes. Anything the provider reports *about* tools —
a tool starting, its output, its completion, a permission request — is a tool
event, never a token, and never ends TTFT. The tooltip says which kind came
first (`reasoning`, `answer` or `tool arguments`).

Provider details:

- **Claude Code**: the first `content_block_start`/`content_block_delta` of a
  main-agent message (`parent_tool_use_id === null`). Subagent output is ignored.
- **Codex**: the first reasoning item start or delta, agent message delta, or
  tool-call argument delta. `item/started` for commands, file changes or MCP calls
  is a tool event.
- **Antigravity and other ACP agents**: the first non-empty `agent_thought_chunk`
  or `agent_message_chunk`. `tool_call` / `tool_call_update` are tool events.

### TTFA — time to first answer

From request sent to the first **non-whitespace visible answer text** (Claude
`text_delta` in the main agent, Codex agent message delta, ACP
`agent_message_chunk`). Reasoning does not count. If the turn produced no
answer text (only tools, or interrupted early) TTFA is unavailable.

### Turn duration

From request sent to the turn's terminal event (completed, interrupted, failed,
cancelled). While the turn runs, the composer shows the elapsed time instead.

### Tool execution duration

Each tool call is timed from its start event to its completion event. Calls
that overlap are merged, so the total is **wall-clock time spent waiting on
tools**, never double counted. The tooltip also shows the call count and the
longest call. For Claude Code a call runs from the end of its `tool_use` block
to its `tool_result`, so a permission prompt you leave open counts as tool
time (never as generation). Calls still open when the turn ends are counted as open and make
the measurement partial.

## Generation speed

Generation time is the sum of **active generation windows**. A window opens at
the first generated token of a model response and closes at its last one. A
model response ends where a tool runs, so tool execution, waiting for approval
and time before the first token (prefill/queueing) are all outside the windows.
**Speed is never computed from the whole turn duration.**

### Average generation tokens/s

`generation tokens ÷ generation time`. A turn with less than **1 s** of
streaming shows `—` ("too short to time"): short replies arrive in a few
network bursts, so any rate would read far too high.

- **Claude Code — exact.** Each main-agent API message reports its final
  `output_tokens` in `message_delta`; those tokens are produced exactly inside
  that message's window. Messages cut short (interrupt, process restart) are
  left out and mark the value partial.
- **Codex — estimated.** Codex reports exact output tokens for the whole turn,
  but not per response, and hidden reasoning can run outside the streamed
  windows. The exact total is divided by the measured windows (`≈`).
- **Antigravity / ACP — estimated**, same as Codex, using the prompt's reported
  usage. Without usage it falls back to streamed characters ÷ 4 (`≈`, tooltip
  says "from characters").

### Live tokens/s

While a turn streams, the composer shows the rate over the **last 2 seconds**,
estimated from streamed answer and reasoning characters (≈ 4 characters per
token). It is always estimated and disappears when the turn ends.

### Peak tokens/s

The highest rate over any **2000 ms sliding window** of the turn's streamed
output. Characters per window are converted to tokens; when an exact output
count exists, the conversion is calibrated so the windows sum to it
("calibrated estimate"). Calibration is skipped when the exact count and the
streamed characters disagree by more than 4× either way (for example hidden,
encrypted reasoning), so hidden output never inflates the peak. Always shown with `≈`. Windows shorter than 2 s at
the start or end of a turn are not used, so a single burst cannot produce an
absurd peak; a turn with less than 2 s of generation has no peak.

## Tokens and context

From the provider's own per-turn usage report:

| Metric | Claude Code | Codex | Antigravity |
| --- | --- | --- | --- |
| Input tokens | exact | exact | exact |
| Output tokens | exact | exact | exact |
| Reasoning tokens | unavailable (folded into output) | exact | exact |
| Cached tokens | exact (cache read) | exact | exact (cache read) |
| Cache hit rate | `cached ÷ input` | same | same |
| Context usage / limit | exact | exact | when reported |

Input tokens include cached and cache-creation tokens, so the cache hit rate is
`cached input ÷ total input` and is never above 100 %.

## Provider, model, reasoning effort, speed

Shown from the turn's model selection (what was requested) and, when it
differs, the model the provider reported actually running. Speed mode is
Claude's fast mode or Codex's service tier (`priority` = fast).

## Other providers

Providers without a stream hook (OpenCode, Cursor, Pi, …) still show turn
duration and whatever usage they report. Timing metrics are unavailable (`—`).

## Settings

**Settings → General → Stats for nerds** turns the feature on. Below it, each
metric has its own switch, plus where stats appear: under the composer
(current and previous turn) and under each reply (that turn's history).
