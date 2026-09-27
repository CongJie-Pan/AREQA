# GPT Image 2.5 Flare - API Pricing & Benchmarks
openai/gpt-image-2.5-flare

Get your API key
Create an API key from your OpenRouter dashboard and set it as an environment variable:

Create API Key

Copy
export OPENROUTER_API_KEY=sk-or-v1-...
2
Generate an image
Use the dedicated Image API with openai/gpt-image-2.5-flare:

Send a prompt and receive generated images as base64-encoded data. Learn more about image generation.

Python
TypeScript (fetch)
cURL

Copy
import requests
import json
import base64

response = requests.post(
  url="https://openrouter.ai/api/v1/images",
  headers={
    "Authorization": "Bearer <OPENROUTER_API_KEY>",
    "Content-Type": "application/json",
  },
  data=json.dumps({
    "model": "openai/gpt-image-2.5-flare",
    "prompt": "A serene mountain landscape at sunset with dramatic clouds"
  })
)

result = response.json()
for i, image in enumerate(result.get("data", [])):
  image_bytes = base64.b64decode(image["b64_json"])
  with open(f"output_{i}.png", "wb") as f:
    f.write(image_bytes)
  print(f"Saved image {i + 1}")
Endpoint
Submits an image generation request. Returns base64-encoded images or streams partial results via SSE.

Docs
POST
https://openrouter.ai/api/v1/images
Authorization
Bearer $OPENROUTER_API_KEY
Content-Type
application/json
HTTP-Referer
optional — your site URL, for rankings
X-Title
optional — your site name, for rankings
Model
openai/gpt-image-2.5-flare
Supported Parameters
Parameter	Type	Values
aspect_ratio	enum	1:1, 3:2, 2:3, 4:3, 3:4, 16:9, 9:16, 21:9, auto
quality	enum	auto, low, medium, high, xhigh, max
background	enum	auto, transparent, opaque
n	range	1–10
input_references	range	0–16
output_compression	range	0–100
Provider Passthrough Parameters
Provider-specific keys accepted under provider.options.

Provider	Parameters
OpenAI	
moderation
