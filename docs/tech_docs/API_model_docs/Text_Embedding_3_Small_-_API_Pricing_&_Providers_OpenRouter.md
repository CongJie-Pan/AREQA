# OpenAI Text Embedding 3 Small - API Pricing & Providers

Get your API key
Create an API key from your OpenRouter dashboard and set it as an environment variable:

Create API Key

Copy
export OPENROUTER_API_KEY=sk-or-v1-...
2
Make your first request
Use openai/text-embedding-3-small with the OpenRouter API:

OpenRouter provides an OpenAI-compatible embeddings API that you can call directly, or using the OpenAI SDK.

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

embedding = client.embeddings.create(
  extra_headers={
    "HTTP-Referer": "<YOUR_SITE_URL>", # Optional. Site URL for rankings on openrouter.ai.
    "X-OpenRouter-Title": "<YOUR_SITE_NAME>", # Optional. Site title for rankings on openrouter.ai.
  },
  model="openai/text-embedding-3-small",
  input="Your text string goes here",
  # input: ["text1", "text2", "text3"] # batch embeddings also supported!
  encoding_format="float"
)
print(embedding.data[0].embedding)
Using third-party SDKs
For information about using third-party SDKs and frameworks with OpenRouter, please see our frameworks documentation.

Endpoint
Submits an embedding request to the embeddings router

POST
https://openrouter.ai/api/v1/embeddings
Authorization
Bearer $OPENROUTER_API_KEY
Content-Type
application/json
HTTP-Referer
optional — your site URL, for rankings
X-Title
optional — your site name, for rankings
Model
openai/text-embedding-3-small
Parameters
Name	Type	Default	Description
seed	integer	—	If specified, the inferencing will sample deterministically, such that repeated requests with the same seed and parameters should return the same result.
max_tokens	integer	—	This sets the upper limit for the number of tokens the model can generate in response.
response_format	map	—	Forces the model to produce specific output format.
temperature	float	1	This setting influences the variety in the model's responses.
top_p	float	1	This setting limits the model's choices to a percentage of likely tokens: only the top tokens whose probabilities add up to P.
stop	array	—	Stop generation immediately if the model encounter any token specified in the stop array.
frequency_penalty	float	0	This setting aims to control the repetition of tokens based on how often they appear in the input.
presence_penalty	float	0	Adjusts how often the model repeats specific tokens already used in the input.
logit_bias	map	—	Accepts a JSON object that maps tokens (specified by their token ID in the tokenizer) to an associated bias value from -100 to 100.
logprobs	boolean	—	Whether to return log probabilities of the output tokens or not.
top_logprobs	integer	—	An integer between 0 and 20 specifying the number of most likely tokens to return at each token position, each with an associated log probability.
