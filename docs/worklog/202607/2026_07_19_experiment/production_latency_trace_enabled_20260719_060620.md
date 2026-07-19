# AREQA Chat Latency Benchmark

Mode: `live`  
Measured runs: `20`

| Variant | Runs | First content median | First content p95 | Completed median | Completed p95 | Visible status | TTFT improvement |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | 20 | 3289.88 ms | 7237.36 ms | 5421.39 ms | 8808.76 ms | 983.50 ms | 0.00% |

> Live results measure client-visible SSE timings; internal phase attribution requires server instrumentation.

## Server Trace Review

The copied backend terminal log showed normal non-recall routes completing in roughly `3.2s` to `4.3s`, with first answer around `1.4s` to `2.4s`. The slow tail came from explicit memory recall: the slow examples recorded `time_to_first_answer_ms` around `6.1s` to `6.5s`, while `provider_first_token_ms` stayed below `500ms`.

The dominant server-side phase was `prompt_assembly`, driven by synchronous `long_term_memory`. In the slow traces, `prompt_assembly` took `4439 ms` to `4647 ms`, and `long_term_memory` took `3914 ms` to `4127 ms`.
