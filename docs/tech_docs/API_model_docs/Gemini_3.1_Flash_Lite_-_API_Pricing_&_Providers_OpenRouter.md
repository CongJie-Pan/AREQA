# Gemini 3.1 Flash Lite - API Pricing & Providers

## Providers

Different companies host the same model. OpenRouter routes your request to one of them based on the routing mode you pick — Balanced (price + speed), Nitro (fastest), or Exacto (one fixed provider).

| Column 1 | Column 2 | Column 3 | Column 4 | Column 5 | Column 6 | Column 7 | Column 8 |
| --- | --- | --- | --- | --- | --- | --- | --- |
|  | $0.25 | $1.50 | $0.025 | $0.05 | 0.93s | 105 tps | 96.70% |
|  | $0.25 | $1.50 | $0.025 | $0.05 | 0.66s | 87 tps | 99.54% |

## Effective Pricing

The chart below shows the average price customers are actually paying after prompt caching. Depending on the amount of repeated context you send, this can be 60–80% cheaper than the provider list price. Shown are rolling averages from the past 30 days.

### Weighted Average

Weighted Avg Input Price

$0.203

/M tokens

Weighted Avg Output Price

$1.47

/M tokens

| Provider | Input $/1M | Output $/1M | Cache hit rate | Token share |
| --- | --- | --- | --- | --- |
| ![Favicon for Google](https://openrouter.ai/images/icons/GoogleVertex.svg)<br>Google Vertex | $0.231 | $1.50 | 9.2% | 60.6% |
| ![Favicon for Google AI Studio](https://openrouter.ai/images/icons/GoogleAIStudio.svg)<br>Google AI Studio | $0.161 | $1.40 | 40.2% | 39.4% |

## Performance

Throughput is how fast the model writes (tokens per second — higher is better). Latency is total round-trip time (lower is better). TTFT is time-to-first-token — how long before you see anything appear (lower is better).

Throughput

105tok/s

best across providers

Latency

0.66s

p50, best provider

### Throughput

Google AI Studio

Avg113 tok/s

Google Vertex

Avg106 tok/s

### Latency

Google AI Studio

Avg0.58 s

Google Vertex

Avg0.94 s

### E2E Latency

Google AI Studio

Avg1.70 s

Google Vertex

Avg2.74 s

## Uptime

Percent of requests that succeeded over the last 30 days. OpenRouter monitors every provider continuously and automatically retries on the next-best provider when one returns an error.

Avg. Provider Uptime (3d)

98.30%

averaged across all endpoints

When an error occurs in an upstream provider, we can recover by routing to another healthy provider, if your request filters allow it. You can access uptime data programmatically through the [Endpoints API](https://openrouter.ai/docs/api/api-reference/endpoints/list-endpoints). [Learn more](https://openrouter.ai/docs/provider-routing) about our load balancing and customization options.

## Apps

Public apps that send the most traffic to this model. Good signal for what real production workloads look like — and a hint at which use cases this model is best suited for.

1.

[Pieces.app: Ambient Artificial Memory](https://openrouter.ai/apps/pieces)

Pieces is a private, on-device, long-term memory layer for macOS, Linux, and Windows that proactively captures your work context as it happens. Over time, Pieces becomes your very own “internet of all context”—browse your artificial memories in the Pieces Desktop app, or plug them into the agents you already use: OpenClaw, Hermes, Claude, Cursor, Codex, etc.

352Btokens

2.

51.4Btokens

3.

32.2Btokens

4.

[Portkey AI](https://openrouter.ai/apps/portkey-ai)

Control panel for AI apps

30.2Btokens

5.

[Claude Code](https://openrouter.ai/apps/claude-code)

Claude Code is Anthropic's agentic coding tool that reads your entire codebase, plans and executes changes across files, runs tests, and iterates on failures, all from natural language prompts.

18.3Btokens

## Activity

Token volume and request traffic to this model over time.

Prompt

70.8B

Completion

3.32B

Reasoning

1.47B

Prompt tokens measure input size. Reasoning tokens show internal thinking before a response. Completion tokens reflect total output length.

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

Use `google/gemini-3.1-flash-lite` with the OpenRouter API:

OpenRouter supports reasoning-enabled models that can show their step-by-step thinking process. Use the `reasoning` parameter in your request to enable reasoning, and access the `reasoning_details` array in the response to see the model's internal reasoning before the final answer. When continuing a conversation, preserve the complete `reasoning_details` when passing messages back to the model so it can continue reasoning from where it left off. [Learn more about reasoning tokens](https://openrouter.ai/docs/use-cases/reasoning-tokens).

In the examples below, the [OpenRouter-specific headers](https://openrouter.ai/docs/requests#request-headers) are optional. Setting them allows your app to appear on the OpenRouter leaderboards.

```
import { OpenRouter } from "@openrouter/sdk";
const openrouter = new OpenRouter({
  apiKey: "<OPENROUTER_API_KEY>"
});
// Stream the response to get reasoning tokens in usage
const stream = await openrouter.chat.send({
  model: "google/gemini-3.1-flash-lite",
  messages: [
    {
      role: "user",
      content: "How many r's are in the word 'strawberry'?"
    }
  ],
  stream: true
});
let response = "";
for await (const chunk of stream) {
  const content = chunk.choices[0]?.delta?.content;
  if (content) {
    response += content;
    process.stdout.write(content);
  }
  // Usage information comes in the final chunk
  if (chunk.usage) {
    console.log("\nReasoning tokens:", chunk.usage.reasoningTokens);
  }
}
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
  "model": "google/gemini-3.1-flash-lite",
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
| `reasoning` | map | — | Controls reasoning behavior for models that support thinking tokens, including whether reasoning is enabled, the reasoning effort, maximum reasoning tokens, and whether reasoning is excluded from the response. |
| `max_tokens` | integer | — | This sets the upper limit for the number of tokens the model can generate in response. |
| `temperature` | float | `1` | This setting influences the variety in the model's responses. |
| `top_p` | float | `1` | This setting limits the model's choices to a percentage of likely tokens: only the top tokens whose probabilities add up to P. |
| `seed` | integer | — | If specified, the inferencing will sample deterministically, such that repeated requests with the same seed and parameters should return the same result. |
| `response_format` | map | — | Forces the model to produce specific output format. |
| `stop` | array | — | Stop generation immediately if the model encounter any token specified in the stop array. |
| `tools` | array | — | Tool calling parameter, following OpenAI's tool calling request shape. |
| `tool_choice` | string or object | — | Controls which (if any) tool is called by the model. |