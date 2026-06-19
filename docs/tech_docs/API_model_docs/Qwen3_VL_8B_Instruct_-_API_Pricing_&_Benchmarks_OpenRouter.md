# Qwen3 VL 8B Instruct - API Pricing & Benchmarks

## Providers

Different companies host the same model. OpenRouter routes your request to one of them based on the routing mode you pick — Balanced (price + speed), Nitro (fastest), or Exacto (one fixed provider).

| Provider | Input /M | Output /M | Cache Read /M | Latency | Throughput | Uptime |
| --- | --- | --- | --- | --- | --- | --- |
|  | $0.08 | $0.50 | \-- | 1.17s | 35 tps | 98.35% |
| 35% off | $0.117 | $0.455 | \-- | 0.52s | 80 tps | 99.94% |
|  | $0.25 | $0.75 | $0.12 | 1.02s | 52 tps | 99.96% |
|  | $0.08 | $0.50 | $0.08 | 0.96s | 41 tps | 97.11% |

## Performance

Throughput is how fast the model writes (tokens per second — higher is better). Latency is total round-trip time (lower is better). TTFT is time-to-first-token — how long before you see anything appear (lower is better).

Throughput

80tok/s

best across providers

Latency

0.52s

p50, best provider

### Throughput

Alibaba Cloud Int.

Avg62 tok/s

Parasail

Avg42 tok/s

NovitaAI

Avg37 tok/s

### Latency

Alibaba Cloud Int.

Avg0.48 s

AtlasCloud

Avg0.62 s

Parasail

Avg0.66 s

### E2E Latency

Alibaba Cloud Int.

Avg1.48 s

Parasail

Avg1.74 s

NovitaAI

Avg2.64 s

### AutoExacto Benchmarks

GPQA DiamondTAU-Bench

AtlasCloud

54.5%\--

Alibaba Cloud Int.

54.8%39.2%

NovitaAI

54.5%34.8%

Parasail

53.4%34.3%

auto-routing

51.3%31.5%

### Tool Call Error Rate

AtlasCloud

Avg1.74 %

NovitaAI

Avg12.45 %

Alibaba Cloud Int.

Avg24.97 %

### Structured Output Error Rate

Parasail

Avg0.14 %

AtlasCloud

Avg0.75 %

Alibaba Cloud Int.

Avg1.46 %

## Pricing

List price is the headline rate per million tokens. Effective price is what you actually pay after prompt caching is applied — for repeated context, this can be 60–80% cheaper. The chart below shows the rolling effective price over the past 30 days.

### Weighted Average

Weighted Avg Input Price

$0.140

/M tokens

Weighted Avg Output Price

$0.597

/M tokens

| Provider | Input $/1M | Output $/1M | Cache hit rate | Token share |
| --- | --- | --- | --- | --- |
| ![Favicon for Parasail](https://t0.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=https://www.parasail.io/&size=256)<br>Parasail | $0.188 | $0.747 | 47.7% | 46.1% |
| ![Favicon for Alibaba](https://t0.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=https://www.alibabacloud.com/&size=256)<br>Alibaba Cloud Int. | $0.117 | $0.452 | 0.0% | 26.7% |
| ![Favicon for AtlasCloud](https://t0.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=https://www.atlascloud.ai/&size=256)<br>AtlasCloud | $0.080 | $0.498 | 0.0% | 15.1% |
| ![Favicon for Novita](https://t0.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=https://novita.ai/&size=256)<br>NovitaAI | $0.080 | $0.498 | 0.0% | 12.0% |

## Benchmarks

Scores on standardized evaluations. Higher percentages are better — and rank percentile shows where this model lands among all models on OpenRouter.

### Reasoning

GPQA Diamond

Graduate-level scientific reasoning

42.7%

HLE

Humanity's Last Exam

2.9%

IFBench

Instruction-following benchmark

32.3%

τ²-Bench Telecom

Conversational AI agents in dual-control scenarios

29.2%

AA-LCR

Long context reasoning evaluation

15.3%

CritPt

Research-level physics reasoning

0.0%

### Coding

SciCode

Python programming for scientific computing

17.4%

Terminal-Bench Hard

Agentic coding & terminal use

2.3%

### Knowledge

AA-Omniscience Accuracy

Proportion of correctly answered questions

20.2%

AA-Omniscience Non-Hallucination Rate

Rate of avoiding hallucination among non-correct responses

9.6%

Metrics sourced from [Artificial Analysis](https://artificialanalysis.ai/models/qwen3-vl-8b-instruct)

## Apps

Public apps that send the most traffic to this model. Good signal for what real production workloads look like — and a hint at which use cases this model is best suited for.

1.

2.5Btokens

2.

931Mtokens

3.

725Mtokens

4.

[Studs.gg](https://openrouter.ai/apps/studsgg)

AI for building Roblox games.

532Mtokens

5.

516Mtokens

## Activity

Token volume and request traffic to this model over time.

Prompt

1.08B

Completion

95.4M

Prompt tokens measure input size. Reasoning tokens show internal thinking before a response. Completion tokens reflect total output length.

## Uptime

Percent of requests that succeeded over the last 30 days. OpenRouter monitors every provider continuously and automatically retries on the next-best provider when one returns an error.

Avg. Provider Uptime (3d)

99.27%

averaged across all endpoints

When an error occurs in an upstream provider, we can recover by routing to another healthy provider, if your request filters allow it. You can access uptime data programmatically through the [Endpoints API](https://openrouter.ai/docs/api/api-reference/endpoints/list-endpoints). [Learn more](https://openrouter.ai/docs/provider-routing) about our load balancing and customization options.

## Quick Start

Drop-in code to call this model. OpenRouter's API is OpenAI-compatible — most SDKs work by just swapping the base URL. The only thing that changes between models is the model slug below.

1

### Get your API key

Create an API key from your OpenRouter dashboard and set it as an environment variable:

[Create API Key](https://openrouter.ai/settings/keys)

```
export OPENROUTER_API_KEY=sk-or-v1-...
```

2

### Make your first request

Use `qwen/qwen3-vl-8b-instruct` with the OpenRouter API:

OpenRouter provides an OpenAI-compatible completion API to 400+ models & providers that you can call directly, or using the OpenAI SDK. Additionally, some third-party SDKs are available.

In the examples below, the [OpenRouter-specific headers](https://openrouter.ai/docs/requests#request-headers) are optional. Setting them allows your app to appear on the OpenRouter leaderboards.

```
from openai import OpenAI
client = OpenAI(
  base_url="https://openrouter.ai/api/v1",
  api_key="<OPENROUTER_API_KEY>",
)
completion = client.chat.completions.create(
  extra_headers={
    "HTTP-Referer": "<YOUR_SITE_URL>", # Optional. Site URL for rankings on openrouter.ai.
    "X-OpenRouter-Title": "<YOUR_SITE_NAME>", # Optional. Site title for rankings on openrouter.ai.
  },
  extra_body={},
  model="qwen/qwen3-vl-8b-instruct",
  messages=[
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "What is in this image?"
        },
        {
          "type": "image_url",
          "image_url": {
            "url": "https://live.staticflickr.com/3851/14825276609_098cac593d_b.jpg"
          }
        }
      ]
    }
  ]
)
print(completion.choices[0].message.content)
```

## Using third-party SDKs

For information about using third-party SDKs and frameworks with OpenRouter, please see our [frameworks documentation](https://openrouter.ai/docs/guides/community/frameworks-and-integrations-overview).

3

### Enable streaming

Add `"stream": true` to your request body to receive responses as server-sent events:

```
curl -N https://openrouter.ai/api/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -d '{
  "model": "qwen/qwen3-vl-8b-instruct",
  "stream": true,
  "messages": [
    {"role": "user", "content": "Hello"}
  ]
}'
```

### Endpoint

Sends a request for a model response for the given chat conversation. Supports both streaming and non-streaming modes.

Creates a streaming or non-streaming response using the OpenAI Responses API format.

[Docs](https://openrouter.ai/docs/api/api-reference/responses/create-responses)

Creates a message using the Anthropic Messages API format. Supports text, images, PDFs, tools, and extended thinking.

[Docs](https://openrouter.ai/docs/api/api-reference/anthropic-messages/create-messages)

### Parameters

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `response_format` | map | — | Forces the model to produce specific output format. |
| `max_tokens` | integer | — | This sets the upper limit for the number of tokens the model can generate in response. |
| `temperature` | float | `0.7` | This setting influences the variety in the model's responses. |
| `top_p` | float | `0.8` | This setting limits the model's choices to a percentage of likely tokens: only the top tokens whose probabilities add up to P. |
| `stop` | array | — | Stop generation immediately if the model encounter any token specified in the stop array. |
| `frequency_penalty` | float | `0` | This setting aims to control the repetition of tokens based on how often they appear in the input. |
| `presence_penalty` | float | `0` | Adjusts how often the model repeats specific tokens already used in the input. |
| `seed` | integer | — | If specified, the inferencing will sample deterministically, such that repeated requests with the same seed and parameters should return the same result. |
| `top_k` | integer | `0` | This limits the model's choice of tokens at each step, making it choose from a smaller set. |
| `repetition_penalty` | float | `1` | Helps to reduce the repetition of tokens from the input. |
| `tools` | array | — | Tool calling parameter, following OpenAI's tool calling request shape. |
| `tool_choice` | string or object | — | Controls which (if any) tool is called by the model. |