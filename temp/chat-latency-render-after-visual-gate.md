# AREQA Chat Latency Benchmark

Mode: `live`  
Measured runs: `1`

| Variant | Runs | First content median | First content p95 | Completed median | Visible status | TTFT improvement |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 1 | 8545.45 ms | 8545.45 ms | 9554.67 ms | 2070.61 ms | 0.00% |

> Live results measure client-visible SSE timings; internal phase attribution requires server logs from `orchestration.turn_trace_summary`.

## Research Findings

- Research question: Which client-visible milestone contributes most to chat response slowness?
- Primary metric: first content time, because it matches the user's perceived wait before an answer starts.
- Secondary metric: completed time, because slow post-token streaming still affects end-to-end responsiveness.
- Attribution boundary: event counts and first-seen timings identify whether the delay happens before routing/status events, before answer content, or during completion.
