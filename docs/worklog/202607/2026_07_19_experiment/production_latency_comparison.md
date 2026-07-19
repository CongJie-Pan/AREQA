# Production Latency Comparison

| Mode | Runs | First content median | First content p95 | Completed median | Completed p95 | Visible status median |
|---|---:|---:|---:|---:|---:|---:|
| Baseline | 5 | 7102.62 ms | 7948.35 ms | 8814.57 ms | 9727.81 ms | 910.08 ms |
| TurnPlan enabled | 5 | 3404.74 ms | 11877.90 ms | 5359.88 ms | 13683.75 ms | 1021.40 ms |
| TurnPlan + production trace | 20 | 3289.88 ms | 7237.36 ms | 5421.39 ms | 8808.76 ms | 983.50 ms |

## Improvement: TurnPlan Enabled vs Baseline

| Metric | Improvement |
|---|---:|
| first_content_median | 52.06% |
| first_content_p95 | -49.44% |
| completed_median | 39.19% |
| completed_p95 | -40.67% |
| visible_status_median | -12.23% |

## Updated Production Trace Result

The 20-run TurnPlan + production trace run reduced first-content median from `7102.62 ms` to `3289.88 ms` and completed median from `8814.57 ms` to `5421.39 ms` compared with the original 5-run baseline. It also improved first-content p95 from `7948.35 ms` to `7237.36 ms` and completed p95 from `9727.81 ms` to `8808.76 ms`.

Server-side trace logs identified the slow tail as explicit memory recall. The slow runs were not dominated by provider first-token latency; they were dominated by `prompt_assembly` because synchronous `long_term_memory` took about `3.9s` to `4.1s`.

Note: the first two rows are 5-run live client-visible SSE benchmarks. The third row is a 20-run live client-visible benchmark after production trace deployment. Server-side phase attribution comes from the copied backend terminal log in `temp/log.md`, not from the benchmark JSON itself.
