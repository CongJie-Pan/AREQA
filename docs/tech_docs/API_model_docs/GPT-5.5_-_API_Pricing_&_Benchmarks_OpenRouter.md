# GPT-5.5 - API Pricing & Benchmarks
openai/gpt-5.5

GPT-5.5 is OpenAI’s frontier model designed for complex professional workloads, building on GPT-5.4 with stronger reasoning, higher reliability, and improved token efficiency on hard tasks. It features a 1M+ token context window (922K input, 128K output) with support for text and image inputs, enabling large-scale reasoning, coding, and multimodal workflows within a single system.

1
Get your API key
Create an API key from your OpenRouter dashboard and set it as an environment variable:

Create API Key

Copy
export OPENROUTER_API_KEY=sk-or-v1-...
2
Make your first request
Use openai/gpt-5.5 with the OpenRouter API:

OpenRouter supports reasoning-enabled models that can show their step-by-step thinking process. Use the reasoning parameter in your request to enable reasoning, and access the reasoning_details array in the response to see the model's internal reasoning before the final answer. When continuing a conversation, preserve the complete reasoning_details when passing messages back to the model so it can continue reasoning from where it left off. Learn more about reasoning tokens.

In the examples below, the OpenRouter-specific headers are optional. Setting them allows your app to appear on the OpenRouter leaderboards.

TypeScript SDK
Python
TypeScript (fetch)
cURL
Python (OpenAI)
TypeScript (OpenAI)

Copy
from openai import OpenAI

client = OpenAI(
  base_url="https://openrouter.ai/api/v1",
  api_key="<OPENROUTER_API_KEY>",
)

# First API call with reasoning
response = client.chat.completions.create(
  model="openai/gpt-5.5",
  messages=[
          {
            "role": "user",
            "content": "How many r's are in the word 'strawberry'?"
          }
        ],
  extra_body={"reasoning": {"enabled": True}}
)

# Extract the assistant message with reasoning_details
response = response.choices[0].message

# Preserve the assistant message with reasoning_details
messages = [
  {"role": "user", "content": "How many r's are in the word 'strawberry'?"},
  {
    "role": "assistant",
    "content": response.content,
    "reasoning_details": response.reasoning_details  # Pass back unmodified
  },
  {"role": "user", "content": "Are you sure? Think carefully."}
]

# Second API call - model continues reasoning from where it left off
response2 = client.chat.completions.create(
  model="openai/gpt-5.5",
  messages=messages,
  extra_body={"reasoning": {"enabled": True}}
)
Using third-party SDKs
For information about using third-party SDKs and frameworks with OpenRouter, please see our frameworks documentation.

3
Enable streaming
Add "stream": true to your request body to receive responses as server-sent events:


Copy
curl -N https://openrouter.ai/api/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -d '{
  "model": "openai/gpt-5.5",
  "stream": true,
  "messages": [
    {"role": "user", "content": "Hello"}
  ]
}'
Endpoint
Sends a request for a model response for the given chat conversation. Supports both streaming and non-streaming modes.

POST
https://openrouter.ai/api/v1/chat/completions
Authorization
Bearer $OPENROUTER_API_KEY
Content-Type
application/json
HTTP-Referer
optional — your site URL, for rankings
X-Title
optional — your site name, for rankings
Model
openai/gpt-5.5
Creates a streaming or non-streaming response using the OpenAI Responses API format.

Docs
POST
https://openrouter.ai/api/v1/responses
Authorization
Bearer $OPENROUTER_API_KEY
Content-Type
application/json
HTTP-Referer
optional — your site URL, for rankings
X-Title
optional — your site name, for rankings
Model
openai/gpt-5.5
Creates a message using the Anthropic Messages API format. Supports text, images, PDFs, tools, and extended thinking.

Docs
POST
https://openrouter.ai/api/v1/messages
Authorization
Bearer $OPENROUTER_API_KEY
Content-Type
application/json
HTTP-Referer
optional — your site URL, for rankings
X-Title
optional — your site name, for rankings
Model
openai/gpt-5.5
Parameters
Name	Type	Default	Description
reasoning	map	—	Controls reasoning behavior for models that support thinking tokens, including whether reasoning is enabled, the reasoning effort, maximum reasoning tokens, and whether reasoning is excluded from the response.
seed	integer	—	If specified, the inferencing will sample deterministically, such that repeated requests with the same seed and parameters should return the same result.
max_tokens	integer	—	This sets the upper limit for the number of tokens the model can generate in response.
response_format	map	—	Forces the model to produce specific output format.
tools	array	—	Tool calling parameter, following OpenAI's tool calling request shape.
tool_choice	string or object	—	Controls which (if any) tool is called by the model.