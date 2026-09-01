# AREQA Chat Latency Benchmark

Mode: `mocked`  
Measured runs: `4`

| Variant | Runs | First content median | First content p95 | Completed median | Visible status | TTFT improvement |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 1 | 176.07 ms | 176.07 ms | 201.28 ms | none | 0.00% |
| no_policy_wait | 1 | 115.85 ms | 115.85 ms | 141.04 ms | none | 34.20% |
| no_cold_memory | 1 | 85.68 ms | 85.68 ms | 110.85 ms | none | 51.34% |
| optimized | 1 | 25.35 ms | 25.35 ms | 50.52 ms | 1.13 ms | 85.60% |

> Mock results validate the experiment mechanics only; they are not production latency measurements.

## Research Findings

- Research question: Which client-visible milestone contributes most to chat response slowness?
- Primary metric: first content time, because it matches the user's perceived wait before an answer starts.
- Secondary metric: completed time, because slow post-token streaming still affects end-to-end responsiveness.
- Attribution boundary: event counts and first-seen timings identify whether the delay happens before routing/status events, before answer content, or during completion.

## Slow Candidates

- `baseline` has no visible status before answer content; users may perceive a blank wait until 176.07 ms.
- `no_policy_wait` has no visible status before answer content; users may perceive a blank wait until 115.85 ms.
- `no_cold_memory` has no visible status before answer content; users may perceive a blank wait until 85.68 ms.
