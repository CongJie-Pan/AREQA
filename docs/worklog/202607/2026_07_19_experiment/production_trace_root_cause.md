# Production Trace Root Cause Review

Source log: [temp/log.md](/workspaces/AREQA/temp/log.md:1)

## Summary

The production trace logs identify the slow tail as explicit memory recall, not provider first-token latency. The slow requests used the `EXPLICIT_MEMORY_RECALL` route and waited for synchronous `long_term_memory` during `prompt_assembly`. Normal non-recall routes were materially faster and skipped the policy classifier or long-term memory when the deterministic TurnPlan allowed it.

## Observed Slow Path

| Run ID | Route | Elapsed | Time to first answer | Provider first token | Top phase | Long-term memory | Evidence |
|---|---|---:|---:|---:|---|---:|---|
| `ad583e56ddd34fda93d8bd073b733d39` | `EXPLICIT_MEMORY_RECALL` | `7399 ms` | `6054 ms` | `497 ms` | `prompt_assembly: 4439 ms` | `3914 ms` | [temp/log.md](/workspaces/AREQA/temp/log.md:99) |
| `5682c05747fc465a9669e7fd8d3c3f52` | `EXPLICIT_MEMORY_RECALL` | `7808 ms` | `6537 ms` | `395 ms` | `prompt_assembly: 4647 ms` | `4127 ms` | [temp/log.md](/workspaces/AREQA/temp/log.md:200) |

Both slow traces recorded `slow_reasons` as `time_to_first_answer` and `top_phase:prompt_assembly`. Both traces also recorded `tool_calls` with `memory_query: 1`, which distinguishes them from the faster non-recall routes.

## Observed Faster Paths

| Run ID | Route | Elapsed | Time to first answer | Model calls | Tool calls | Evidence |
|---|---|---:|---:|---|---|---|
| `c37b1612f8074a8083d17986a23ad890` | `SENSITIVE_NO_RECALL` | `3618 ms` | `1640 ms` | `main_answer`, `suggestions` | `hot_memory` | [temp/log.md](/workspaces/AREQA/temp/log.md:31) |
| `f4c35bbdbc5c4b9ba54837d507b35156` | `SENSITIVE_NO_RECALL` | `3229 ms` | `1566 ms` | `main_answer`, `suggestions` | `hot_memory` | [temp/log.md](/workspaces/AREQA/temp/log.md:127) |
| `8f85fa8c98574c8b947ea9d48c7f48b4` | `SENSITIVE_NO_RECALL` | `3322 ms` | `1479 ms` | `main_answer`, `suggestions` | `hot_memory` | [temp/log.md](/workspaces/AREQA/temp/log.md:230) |

The learning-help route still ran `policy_classifier`, but it skipped long-term memory when the route did not require explicit recall. Example evidence: [temp/log.md](/workspaces/AREQA/temp/log.md:69) and [temp/log.md](/workspaces/AREQA/temp/log.md:53).

## Interpretation

The provider was not the dominant slow-tail cause in the copied trace window. In the slow explicit-recall runs, the main model started late (`5557 ms` to `6142 ms`), but once started, first token latency was only `395 ms` to `497 ms`. The blocking work happened before `main_model_started`.

The highest-confidence root cause is synchronous long-term memory retrieval inside prompt assembly. This is directly supported by the slow traces: `prompt_assembly` was the top phase, and `long_term_memory` accounted for most of that duration.

Suggestions remain a secondary completion-latency cost. Across the reviewed traces, suggestions often took roughly `766 ms` to `1198 ms`. This does not explain slow first answer, but it does delay terminal completion.

## Recommended Next Changes

1. Add a bounded timeout for explicit-recall long-term memory, likely `1500 ms` to `2000 ms`, with a safe fallback that starts the answer without blocking indefinitely.
2. Add a short-lived memory-query cache for repeated recall-like questions from the same user/session.
3. Move or bound suggestions so they do not add about one second to terminal completion.
4. Re-evaluate whether `policy_classifier` is required for every `LEARNING_HELP` route; it costs roughly `594 ms` to `877 ms` in the reviewed traces.

## Conclusion

TurnPlan is effective for non-recall paths, and production trace evidence now identifies the remaining slow tail. The next optimization should target explicit memory recall timeout/caching before broad Phase 3 parallelization.
