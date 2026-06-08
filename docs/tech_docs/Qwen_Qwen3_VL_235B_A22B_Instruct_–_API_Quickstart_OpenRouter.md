# Qwen: Qwen3 VL 235B A22B Instruct – API Quickstart

Qwen3-VL-235B-A22B Instruct is an open-weight multimodal model that unifies strong text generation with visual understanding across images and video. The Instruct model targets general vision-language use (VQA, document parsing, chart/table extraction, multilingual OCR). The series emphasizes robust perception (recognition of diverse real-world and synthetic categories), spatial understanding (2D/3D grounding), and long-form visual comprehension, with competitive results on public multimodal benchmarks for both perception and reasoning.

Beyond analysis, Qwen3-VL supports agentic interaction and tool use: it can follow complex instructions over multi-image, multi-turn dialogues; align text to video timelines for precise temporal queries; and operate GUI elements for automation tasks. The models also enable visual coding workflows—turning sketches or mockups into code and assisting with UI debugging—while maintaining strong text-only performance comparable to the flagship Qwen3 language models. This makes Qwen3-VL suitable for production scenarios spanning document AI, multilingual OCR, software/UI assistance, spatial/embodied tasks, and research on vision-language agents.

Modalities

Input Price

$0.20/M

Output Price

$0.88/M

Context

262K

Weekly Tokens

13.1B

Released

Sep 24, 2025

## Sample code and API for Qwen3 VL 235B A22B Instruct

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
qwen/qwen3-vl-235b-a22b-instruct
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

  model="qwen/qwen3-vl-235b-a22b-instruct",

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

  "model": "qwen/qwen3-vl-235b-a22b-instruct",

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
0.7
```
 | This setting influences the variety in the model's responses. |
 
```
top_p
```
 | float | 
```
0.8
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
logit_bias
```
 | map | — | Accepts a JSON object that maps tokens (specified by their token ID in the tokenizer) to an associated bias value from -100 to 100. |
 
```
tools
```
 | array | — | Tool calling parameter, following OpenAI's tool calling request shape. |
 
```
tool_choice
```
 | string or object | — | Controls which (if any) tool is called by the model. |

## More models from [Qwen](https://openrouter.ai/qwen)