# Qwen3 Embedding 8B - API Pricing & Providers

## Providers

Different companies host the same model. OpenRouter routes your request to one of them based on the routing mode you pick — Balanced (price + speed), Nitro (fastest), or Exacto (one fixed provider).

| Provider | Input /M | Latency | Uptime |
| --- | --- | --- | --- |
|  | $0.01 | \-- | 100.00% |
|  | $0.01 | \-- | 100.00% |
|  | $0.04 | \-- | 99.90% |

## Performance

Throughput is how fast the model writes (tokens per second — higher is better). Latency is total round-trip time (lower is better). TTFT is time-to-first-token — how long before you see anything appear (lower is better).

## Pricing

List price is the headline rate per million tokens. Effective price is what you actually pay after prompt caching is applied — for repeated context, this can be 60–80% cheaper. The chart below shows the rolling effective price over the past 30 days.

### Weighted Average

Weighted Avg Input Price

$0.011

/M tokens

Weighted Avg Output Price

$0.0000

/M tokens

| Provider | Input $/1M | Output $/1M | Cache hit rate | Token share |
| --- | --- | --- | --- | --- |
| ![Favicon for Nebius](https://t0.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=https://docs.nebius.com/&size=256)<br>Nebius Token Factory | $0.0098 | $0.0000 | 0.0% | 51.5% |
| ![Favicon for DeepInfra](https://openrouter.ai/images/icons/DeepInfra.webp)<br>DeepInfra | $0.0097 | $0.0000 | 0.0% | 44.9% |
| ![Favicon for SiliconFlow](https://openrouter.ai/images/icons/SiliconFlow.svg)<br>SiliconFlow | $0.040 | $0.0000 | 0.0% | 3.6% |

## Apps

Public apps that send the most traffic to this model. Good signal for what real production workloads look like — and a hint at which use cases this model is best suited for.

1.

23.2Btokens

2.

2.48Btokens

3.

2.32Btokens

4.

2.03Btokens

5.

1.79Btokens

## Activity

Token volume and request traffic to this model over time.

Prompt

30.5B

Completion

0

Prompt tokens measure input size. Reasoning tokens show internal thinking before a response. Completion tokens reflect total output length.

## Uptime

Percent of requests that succeeded over the last 30 days. OpenRouter monitors every provider continuously and automatically retries on the next-best provider when one returns an error.

Avg. Provider Uptime (3d)

99.90%

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

Use `qwen/qwen3-embedding-8b` with the OpenRouter API:

OpenRouter provides an OpenAI-compatible embeddings API that you can call directly, or using the OpenAI SDK.

In the examples below, the [OpenRouter-specific headers](https://openrouter.ai/docs/requests#request-headers) are optional. Setting them allows your app to appear on the OpenRouter leaderboards.

```
from openai import OpenAI
client = OpenAI(
  base_url="https://openrouter.ai/api/v1",
  api_key="<OPENROUTER_API_KEY>",
)
embedding = client.embeddings.create(
  extra_headers={
    "HTTP-Referer": "<YOUR_SITE_URL>", # Optional. Site URL for rankings on openrouter.ai.
    "X-OpenRouter-Title": "<YOUR_SITE_NAME>", # Optional. Site title for rankings on openrouter.ai.
  },
  model="qwen/qwen3-embedding-8b",
  input="Your text string goes here",
  # input: ["text1", "text2", "text3"] # batch embeddings also supported!
  encoding_format="float"
)
print(embedding.data[0].embedding)
```

## Using third-party SDKs

For information about using third-party SDKs and frameworks with OpenRouter, please see our [frameworks documentation](https://openrouter.ai/docs/guides/community/frameworks-and-integrations-overview).

### Endpoint

Submits an embedding request to the embeddings router

### Parameters

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `max_tokens` | integer | — | This sets the upper limit for the number of tokens the model can generate in response. |
| `temperature` | float | `1` | This setting influences the variety in the model's responses. |
| `top_p` | float | `1` | This setting limits the model's choices to a percentage of likely tokens: only the top tokens whose probabilities add up to P. |
| `stop` | array | — | Stop generation immediately if the model encounter any token specified in the stop array. |
| `frequency_penalty` | float | `0` | This setting aims to control the repetition of tokens based on how often they appear in the input. |
| `presence_penalty` | float | `0` | Adjusts how often the model repeats specific tokens already used in the input. |
| `seed` | integer | — | If specified, the inferencing will sample deterministically, such that repeated requests with the same seed and parameters should return the same result. |
| `top_k` | integer | `0` | This limits the model's choice of tokens at each step, making it choose from a smaller set. |
| `logit_bias` | map | — | Accepts a JSON object that maps tokens (specified by their token ID in the tokenizer) to an associated bias value from -100 to 100. |
| `logprobs` | boolean | — | Whether to return log probabilities of the output tokens or not. |
| `top_logprobs` | integer | — | An integer between 0 and 20 specifying the number of most likely tokens to return at each token position, each with an associated log probability. |