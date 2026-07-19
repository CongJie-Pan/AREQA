# Production Latency Comparison

| Mode | Runs | First content median | First content p95 | Completed median | Completed p95 | Visible status median |
|---|---:|---:|---:|---:|---:|---:|
| Baseline | 5 | 7102.62 ms | 7948.35 ms | 8814.57 ms | 9727.81 ms | 910.08 ms |
| TurnPlan enabled | 5 | 3404.74 ms | 11877.90 ms | 5359.88 ms | 13683.75 ms | 1021.40 ms |

## Improvement: TurnPlan Enabled vs Baseline

| Metric | Improvement |
|---|---:|
| first_content_median | 52.06% |
| first_content_p95 | -49.44% |
| completed_median | 39.19% |
| completed_p95 | -40.67% |
| visible_status_median | -12.23% |

Note: both runs are live client-visible SSE benchmarks. They do not include server-side internal phase attribution unless production logs are separately inspected.
