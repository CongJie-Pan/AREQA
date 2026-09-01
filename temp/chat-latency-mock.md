# AREQA Chat Latency Benchmark

Mode: `mocked`  
Measured runs: `20`

| Variant | Runs | First content median | First content p95 | Completed median | Visible status | TTFT improvement |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 5 | 176.37 ms | 176.91 ms | 201.51 ms | none | 0.00% |
| no_policy_wait | 5 | 116.17 ms | 116.28 ms | 141.31 ms | none | 34.13% |
| no_cold_memory | 5 | 85.92 ms | 86.43 ms | 111.08 ms | none | 51.28% |
| optimized | 5 | 25.51 ms | 25.83 ms | 50.70 ms | 1.15 ms | 85.54% |

> Mock results validate the experiment mechanics only; they are not production latency measurements.

## Research Findings

- Research question: Which client-visible milestone contributes most to chat response slowness?
- Primary metric: first content time, because it matches the user's perceived wait before an answer starts.
- Secondary metric: completed time, because slow post-token streaming still affects end-to-end responsiveness.
- Attribution boundary: event counts and first-seen timings identify whether the delay happens before routing/status events, before answer content, or during completion.

## Slow Candidates

- `baseline` has no visible status before answer content; users may perceive a blank wait until 176.37 ms.
- `no_policy_wait` has no visible status before answer content; users may perceive a blank wait until 116.17 ms.
- `no_cold_memory` has no visible status before answer content; users may perceive a blank wait until 85.92 ms.
