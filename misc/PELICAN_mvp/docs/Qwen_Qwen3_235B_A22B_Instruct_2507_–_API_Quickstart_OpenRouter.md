# Qwen: Qwen3 235B A22B Instruct 2507 – API Quickstart

Qwen3-235B-A22B-Instruct-2507 is a multilingual, instruction-tuned mixture-of-experts language model based on the Qwen3-235B architecture, with 22B active parameters per forward pass. It is optimized for general-purpose text generation, including instruction following, logical reasoning, math, code, and tool usage. The model supports a native 262K context length and does not implement "thinking mode" (<think> blocks).

Compared to its base variant, this version delivers significant gains in knowledge coverage, long-context reasoning, coding benchmarks, and alignment with open-ended tasks. It is particularly strong on multilingual understanding, math reasoning (e.g., AIME, HMMT), and alignment evaluations like Arena-Hard and WritingBench.

Modalities

Input Price

$0.071/M

Output Price

$0.10/M

Context

262K

Weekly Tokens

286B

Released

Jul 22, 2025

## Sample code and API for Qwen3 235B A22B Instruct 2507

### OpenRouter normalizes requests and responses across providers for you.

1

### Get your API key

Create an API key from your OpenRouter dashboard and set it as an environment variable:

```


export OPENROUTER_API_KEY=sk-or-v1-...


```

2

### Make your first request

Use 
```
qwen/qwen3-235b-a22b-2507
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

  model="qwen/qwen3-235b-a22b-2507",

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

  "model": "qwen/qwen3-235b-a22b-2507",

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
stop
```
 | array | — | Stop generation immediately if the model encounter any token specified in the stop array. |
 
```
frequency_penalty
```
 | float | 
```
0
```
 | This setting aims to control the repetition of tokens based on how often they appear in the input. |
 
```
presence_penalty
```
 | float | 
```
0
```
 | Adjusts how often the model repeats specific tokens already used in the input. |
 
```
repetition_penalty
```
 | float | 
```
1
```
 | Helps to reduce the repetition of tokens from the input. |
 
```
top_k
```
 | integer | 
```
0
```
 | This limits the model's choice of tokens at each step, making it choose from a smaller set. |
 
```
seed
```
 | integer | — | If specified, the inferencing will sample deterministically, such that repeated requests with the same seed and parameters should return the same result. |
 
```
min_p
```
 | float | 
```
0
```
 | Represents the minimum probability for a token to be considered, relative to the probability of the most likely token. |
 
```
response_format
```
 | map | — | Forces the model to produce specific output format. |
 
```
tools
```
 | array | — | Tool calling parameter, following OpenAI's tool calling request shape. |
 
```
tool_choice
```
 | string or object | — | Controls which (if any) tool is called by the model. |
 
```
logit_bias
```
 | map | — | Accepts a JSON object that maps tokens (specified by their token ID in the tokenizer) to an associated bias value from -100 to 100. |

## More models from [Qwen](https://openrouter.ai/qwen)