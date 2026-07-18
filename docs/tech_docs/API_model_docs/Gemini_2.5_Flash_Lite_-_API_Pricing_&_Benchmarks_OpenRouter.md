# Gemini 2.5 Flash Lite - API Pricing & Benchmarks
google/gemini-2.5-flash-lite

Quick Start
Drop-in code to call this model with OpenRouter's OpenAI-compatible API.

1
Get your API key
Create an API key from your OpenRouter dashboard and set it as an environment variable:

Create API Key

Copy
export OPENROUTER_API_KEY=sk-or-v1-...
2
Make your first request
Use google/gemini-2.5-flash-lite with the OpenRouter API:

OpenRouter provides an OpenAI-compatible completion API to 400+ models & providers that you can call directly, or using the OpenAI SDK. Additionally, some third-party SDKs are available.

In the examples below, the OpenRouter-specific headers are optional. Setting them allows your app to appear on the OpenRouter leaderboards.

TypeScript SDK
Python SDK
Go SDK
Python
TypeScript (fetch)
cURL
Python (OpenAI)
TypeScript (OpenAI)
TypeScript (Anthropic)
Go (Anthropic)

Copy
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
  model="google/gemini-2.5-flash-lite",
  messages=[
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "What is in this image, audio and video?"
        },
        {
          "type": "image_url",
          "image_url": {
            "url": "https://live.staticflickr.com/3851/14825276609_098cac593d_b.jpg"
          }
        },
        {
          "type": "input_audio",
          "input_audio": {
            "data": "UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB",
            "format": "wav"
          }
        },
        {
          "type": "video_url",
          "video_url": {
            "url": "https://storage.googleapis.com/cloud-samples-data/video/JaneGoodall.mp4"
          }
        }
      ]
    }
  ]
)
print(completion.choices[0].message.content)
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
  "model": "google/gemini-2.5-flash-lite",
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
google/gemini-2.5-flash-lite
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
google/gemini-2.5-flash-lite
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
google/gemini-2.5-flash-lite
Parameters
Name	Type	Default	Description
reasoning	map	—	Controls reasoning behavior for models that support thinking tokens, including whether reasoning is enabled, the reasoning effort, maximum reasoning tokens, and whether reasoning is excluded from the response.
response_format	map	—	Forces the model to produce specific output format.
max_tokens	integer	—	This sets the upper limit for the number of tokens the model can generate in response.
temperature	float	1	This setting influences the variety in the model's responses.
top_p	float	1	This setting limits the model's choices to a percentage of likely tokens: only the top tokens whose probabilities add up to P.
seed	integer	—	If specified, the inferencing will sample deterministically, such that repeated requests with the same seed and parameters should return the same result.
tools	array	—	Tool calling parameter, following OpenAI's tool calling request shape.
tool_choice	string or object	—	Controls which (if any) tool is called by the model.
stop	array	—	Stop generation immediately if the model encounter any token specified in the stop array.