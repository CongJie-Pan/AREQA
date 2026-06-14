# Qwen: Qwen3.5 397B A17B – API Quickstart

The Qwen3.5 series 397B-A17B native vision-language model is built on a hybrid architecture that integrates a linear attention mechanism with a sparse mixture-of-experts model, achieving higher inference efficiency. It delivers state-of-the-art performance comparable to leading-edge models across a wide range of tasks, including language understanding, logical reasoning, code generation, agent-based tasks, image understanding, video understanding, and graphical user interface (GUI) interactions. With its robust code-generation and agent capabilities, the model exhibits strong generalization across diverse agent.

Modalities

Input Price

35% off

$0.39/M

Output Price

35% off

$2.34/M

Context

262K

Weekly Tokens

38.2B

Released

Feb 16, 2026

## Sample code and API for Qwen3.5 397B A17B

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
qwen/qwen3.5-397b-a17b
```
 with the OpenRouter API:

OpenRouter supports reasoning-enabled models that can show their step-by-step thinking process. Use the 
```
reasoning
```
 parameter in your request to enable reasoning, and access the 
```
reasoning_details
```
 array in the response to see the model's internal reasoning before the final answer. When continuing a conversation, preserve the complete 
```
reasoning_details
```
 when passing messages back to the model so it can continue reasoning from where it left off. [Learn more about reasoning tokens](https://openrouter.ai/docs/use-cases/reasoning-tokens).

In the examples below, the [OpenRouter-specific headers](https://openrouter.ai/docs/requests#request-headers) are optional. Setting them allows your app to appear on the OpenRouter leaderboards.

```


import requests

import json

# First API call with reasoning

response = requests.post(

  url="https://openrouter.ai/api/v1/chat/completions",

  headers={

    "Authorization": "Bearer <OPENROUTER_API_KEY>",

    "Content-Type": "application/json",

  },

  data=json.dumps({

    "model": "qwen/qwen3.5-397b-a17b",

    "messages": [

        {

          "role": "user",

          "content": "How many r's are in the word 'strawberry'?"

        }

      ],

    "reasoning": {"enabled": True}

  })

)

# Extract the assistant message with reasoning_details

response = response.json()

response = response['choices'][0]['message']

# Preserve the assistant message with reasoning_details

messages = [

  {"role": "user", "content": "How many r's are in the word 'strawberry'?"},

  {

    "role": "assistant",

    "content": response.get('content'),

    "reasoning_details": response.get('reasoning_details')  # Pass back unmodified

  },

  {"role": "user", "content": "Are you sure? Think carefully."}

]

# Second API call - model continues reasoning from where it left off

response2 = requests.post(

  url="https://openrouter.ai/api/v1/chat/completions",

  data=json.dumps({

    "model": "qwen/qwen3.5-397b-a17b",

    "messages": messages,  # Includes preserved reasoning_details

    "reasoning": {"enabled": True}

  })

)


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

  "model": "qwen/qwen3.5-397b-a17b",

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
reasoning
```
 | map | — | Controls reasoning behavior for models that support thinking tokens, including whether reasoning is enabled, the reasoning effort, maximum reasoning tokens, and whether reasoning is excluded from the response. |
 
```
max_tokens
```
 | integer | — | This sets the upper limit for the number of tokens the model can generate in response. |
 
```
temperature
```
 | float | 
```
0.6
```
 | This setting influences the variety in the model's responses. |
 
```
top_p
```
 | float | 
```
0.95
```
 | This setting limits the model's choices to a percentage of likely tokens: only the top tokens whose probabilities add up to P. |
 
```
seed
```
 | integer | — | If specified, the inferencing will sample deterministically, such that repeated requests with the same seed and parameters should return the same result. |
 
```
presence_penalty
```
 | float | 
```
0
```
 | Adjusts how often the model repeats specific tokens already used in the input. |
 
```
response_format
```
 | map | — | Forces the model to produce specific output format. |
 
```
tool_choice
```
 | string or object | — | Controls which (if any) tool is called by the model. |
 
```
tools
```
 | array | — | Tool calling parameter, following OpenAI's tool calling request shape. |

## More models from [Qwen](https://openrouter.ai/qwen)