# Qwen3 30B A3B Instruct 2507 - API Pricing & Benchmark

## Providers

Different companies host the same model. OpenRouter routes your request to one of them based on the routing mode you pick — Balanced (price + speed), Nitro (fastest), or Exacto (one fixed provider).

 Provider | Input $/M | Output $/M | Latency | Throughput | Uptime |  |
| --- | --- | --- | --- | --- | --- | --- |
 
![Favicon for StreamLake](https://t0.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=https://www.streamlake.com/&size=256)

StreamLake



 | $0.04815 | $0.1931 | 

2.13s

 | 

20 tps

 | 

99.57%

 |  |
 

![Favicon for Nebius](https://t0.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=https://docs.nebius.com/&size=256)

Nebius Token Factory



 | $0.10 | $0.30 | 

0.25s

 | 

54 tps

 | 

98.04%

 |  |
 

![Favicon for AtlasCloud](https://t0.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=https://www.atlascloud.ai/&size=256)

AtlasCloud



 | $0.10 | $0.30 | 

2.33s

 | 

25 tps

 | 

99.79%

 |  |
 

![Favicon for WandB](https://t0.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=https://wandb.ai/home&size=256)

Weights & Biases



 | $0.10 | $0.30 | 

0.22s

 | 

61 tps

 | 

100%

 |  |
 

![Favicon for Alibaba](https://t0.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=https://www.alibabacloud.com/&size=256)

Alibaba Cloud Int.



 | $0.20$0.13 | $0.80$0.52 | 

0.38s

 | 

55 tps

 | 

99.37%

 |  |
 

![Favicon for SiliconFlow](https://openrouter.ai/images/icons/SiliconFlow.svg)

SiliconFlow



 | $0.09 | $0.30 | 

2.61s

 | 

14 tps

 | 

84.38%

 |  |

## Performance

Throughput is how fast the model writes (tokens per second — higher is better). Latency is total round-trip time (lower is better). TTFT is time-to-first-token — how long before you see anything appear (lower is better).

Throughput

61tok/s

best across providers

Latency

0.22s

p50, best provider

### Throughput

Alibaba Cloud Int.

Avg60 tok/s

Weights & Biases

Avg54 tok/s

Nebius Token Factory

Avg44 tok/s

### Latency

Weights & Biases

Avg0.23 s

Nebius Token Factory

Avg0.31 s

Alibaba Cloud Int.

Avg0.39 s

### E2E Latency

Weights & Biases

Avg1.40 s

Alibaba Cloud Int.

Avg1.53 s

Nebius Token Factory

Avg1.92 s

### Tool Call Error Rate

Nebius Token Factory

Avg0.78 %

StreamLake

Avg5.02 %

AtlasCloud

Avg6.18 %

### Structured Output Error Rate

Nebius Token Factory

Avg0.13 %

AtlasCloud

Avg0.21 %

SiliconFlow

Avg0.27 %

## Pricing

List price is the headline rate per million tokens. Effective price is what you actually pay after prompt caching is applied — for repeated context, this can be 60–80% cheaper. The chart below shows the rolling effective price over the past 30 days.

Weighted Avg Input Price

$0.098

/M tokens

Weighted Avg Output Price

$0.298

/M tokens

 Provider | Input $/1M | Output $/1M | Cache hit rate | Token share |
| --- | --- | --- | --- | --- |
 
![Favicon for WandB](https://t0.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=https://wandb.ai/home&size=256)

Weights & Biases



 | $0.100 | $0.297 | 11.6% | 

40.6%



 |
 

![Favicon for Nebius](https://t0.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=https://docs.nebius.com/&size=256)

Nebius Token Factory



 | $0.100 | $0.292 | 13.1% | 

17.5%



 |
 

![Favicon for SiliconFlow](https://openrouter.ai/images/icons/SiliconFlow.svg)

SiliconFlow



 | $0.089 | $0.293 | 0.0% | 

13.5%



 |
 

![Favicon for Alibaba](https://t0.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=https://www.alibabacloud.com/&size=256)

Alibaba Cloud Int.



 | $0.130 | $0.511 | 0.0% | 

11.2%



 |
 

![Favicon for AtlasCloud](https://t0.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=https://www.atlascloud.ai/&size=256)

AtlasCloud



 | $0.098 | $0.297 | 8.6% | 

9.7%



 |
 

![Favicon for StreamLake](https://t0.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=https://www.streamlake.com/&size=256)

StreamLake



 | $0.047 | $0.186 | 18.5% | 

7.5%



 |

## Benchmarks

Scores on standardized evaluations. Higher percentages are better — and rank percentile shows where this model lands among all models on OpenRouter.

### Reasoning

GPQA Diamond

Graduate-level scientific reasoning

65.9%

HLE

Humanity's Last Exam

6.8%

IFBench

Instruction-following benchmark

33.1%

τ²-Bench Telecom

Conversational AI agents in dual-control scenarios

10.2%

AA-LCR

Long context reasoning evaluation

22.7%

GDPval-AA

Economically valuable tasks

0.7%

CritPt

Research-level physics reasoning

0.0%

### Coding

SciCode

Python programming for scientific computing

30.4%

Terminal-Bench Hard

Agentic coding & terminal use

6.1%

### Knowledge

AA-Omniscience Accuracy

Proportion of correctly answered questions

15.1%

AA-Omniscience Non-Hallucination Rate

Rate of avoiding hallucination among non-correct responses

4.6%

Metrics sourced from [Artificial Analysis](https://artificialanalysis.ai/models/qwen3-30b-a3b-2507)

## Apps

Public apps that send the most traffic to this model. Good signal for what real production workloads look like — and a hint at which use cases this model is best suited for.

1.

6.62Btokens

2.

4.55Btokens

3.

4.1Btokens

4.

[OpenClaw](https://openrouter.ai/apps/openclaw)

OpenClaw is an open-source AI agent that connects to your messaging apps and takes real actions on your behalf, from running commands and browsing the web to managing files and sending emails.

1.24Btokens

5.

[Hermes Agent](https://openrouter.ai/apps/hermes-agent)

Hermes Agent is an open-source, self-improving AI agent by Nous Research that runs persistently with memory across sessions, and builds reusable skills from experience. It comes with 40+ built-in tools, including web search, browser automation, and vision, plus scheduled automations and subagents.

949Mtokens

## Activity

Token volume and request traffic to this model over time.

Prompt

471M

Completion

46.7M

Prompt tokens measure input size. Reasoning tokens show internal thinking before a response. Completion tokens reflect total output length.

## Uptime

Percent of requests that succeeded over the last 30 days. OpenRouter monitors every provider continuously and automatically retries on the next-best provider when one returns an error.

Avg. Provider Uptime (3d)

95.97%

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

Use 
```
qwen/qwen3-30b-a3b-instruct-2507
```
 with the OpenRouter API:

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

  model="qwen/qwen3-30b-a3b-instruct-2507",

  messages=[

    {

      "role": "user",

      "content": "What is the meaning of life?"

    }

  ]

)

print(completion.choices[0].message.content)


```

## Using third-party SDKs

For information about using third-party SDKs and frameworks with OpenRouter, please see our [frameworks documentation](https://openrouter.ai/docs/guides/community/frameworks-and-integrations-overview).

3

### Enable streaming

Add 
```
"stream": true
```
 to your request body to receive responses as server-sent events:

```


curl -N https://openrouter.ai/api/v1/chat/completions \

  -H "Content-Type: application/json" \

  -H "Authorization: Bearer $OPENROUTER_API_KEY" \

  -d '{

  "model": "qwen/qwen3-30b-a3b-instruct-2507",

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

 Name | Type | Default | Description |
| --- | --- | --- | --- |
 
```
max_tokens
```
 | integer | — | This sets the upper limit for the number of tokens the model can generate in response. |
 
```
temperature
```
 | float | 
```
1
```
 | This setting influences the variety in the model's responses. |
 
```
top_p
```
 | float | 
```
1
```
 | This setting limits the model's choices to a percentage of likely tokens: only the top tokens whose probabilities add up to P. |
 
```
frequency_penalty
```
 | float | 
```
0
```
 | This setting aims to control the repetition of tokens based on how often they appear in the input. |
 
```
stop
```
 | array | — | Stop generation immediately if the model encounter any token specified in the stop array. |
 
```
presence_penalty
```
 | float | 
```
0
```
 | Adjusts how often the model repeats specific tokens already used in the input. |
 
```
tools
```
 | array | — | Tool calling parameter, following OpenAI's tool calling request shape. |
 
```
tool_choice
```
 | string or object | — | Controls which (if any) tool is called by the model. |