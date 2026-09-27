# Qwen Image 3 Pro - API Pricing & Benchmarks
qwen/qwen-image-3-pro

1
Get your API key
Create an API key from your OpenRouter dashboard and set it as an environment variable:

Create API Key

Copy
export OPENROUTER_API_KEY=sk-or-v1-...
2
Generate an image
Use the dedicated Image API with qwen/qwen-image-3-pro:

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
    "model": "qwen/qwen-image-3-pro",
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
qwen/qwen-image-3-pro
Supported Parameters
Parameter	Type	Values
resolution	enum	1K, 2K
aspect_ratio	enum	1:1, 1:2, 1:4, 2:1, 2:3, 3:2, 3:4, 4:1, 4:3, 4:5, 5:4, 9:16, 16:9
n	range	1–6
input_references	range	0–4
seed	boolean	Supported