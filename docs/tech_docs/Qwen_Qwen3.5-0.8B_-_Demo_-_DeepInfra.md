# Qwen/Qwen3.5-0.8B - Demo - DeepInfra

---

library\_name: transformers license: apache-2.0 license\_link: [https://huggingface.co/Qwen/Qwen3.5-0.8B/blob/main/LICENSE](https://huggingface.co/Qwen/Qwen3.5-0.8B/blob/main/LICENSE) pipeline\_tag: image-text-to-text base\_model:

-   Qwen/Qwen3.5-0.8B-Base
---

## Qwen3.5-0.8B

![](https://qianwen-res.oss-accelerate.aliyuncs.com/logo_qwen3.5.png)

[![Qwen Chat](https://img.shields.io/badge/%F0%9F%92%9C%EF%B8%8F%20Qwen%20Chat%20-536af5)](https://chat.qwen.ai/)

> \[!Note\] This repository contains model weights and configuration files for the post-trained model in the Hugging Face Transformers format.
> 
> These artifacts are compatible with Hugging Face Transformers, vLLM, SGLang, KTransformers, etc.
> 
> In light of its parameter scale, the intended use cases are prototyping, task-specific fine-tuning, and other research or development purposes.

Over recent months, we have intensified our focus on developing foundation models that deliver exceptional utility and performance. Qwen3.5 represents a significant leap forward, integrating breakthroughs in multimodal learning, architectural efficiency, reinforcement learning scale, and global accessibility to empower developers and enterprises with unprecedented capability and efficiency.

## Qwen3.5 Highlights

Qwen3.5 features the following enhancement:

-   **Unified Vision-Language Foundation**: Early fusion training on multimodal tokens achieves cross-generational parity with Qwen3 and outperforms Qwen3-VL models across reasoning, coding, agents, and visual understanding benchmarks.
    
-   **Efficient Hybrid Architecture**: Gated Delta Networks combined with sparse Mixture-of-Experts deliver high-throughput inference with minimal latency and cost overhead.
    
-   **Scalable RL Generalization**: Reinforcement learning scaled across million-agent environments with progressively complex task distributions for robust real-world adaptability.
    
-   **Global Linguistic Coverage**: Expanded support to 201 languages and dialects, enabling inclusive, worldwide deployment with nuanced cultural and regional understanding.
    
-   **Next-Generation Training Infrastructure**: Near-100% multimodal training efficiency compared to text-only training and asynchronous RL frameworks supporting massive-scale agent scaffolds and environment orchestration.

For more details, please refer to our blog post [Qwen3.5](https://qwen.ai/blog?id=qwen3.5).

## Model Overview

-   Type: Causal Language Model with Vision Encoder
-   Training Stage: Pre-training & Post-training
-   Language Model  -   Number of Parameters: 0.8B
      -   Hidden Dimension: 1024
      -   Token Embedding: 248320 (Padded)
      -   Number of Layers: 24
      -   Hidden Layout: 6 × (3 × (Gated DeltaNet → FFN) → 1 × (Gated Attention → FFN))
      -   Gated DeltaNet:    -   Number of Linear Attention Heads: 16 for V and 16 for QK
              -   Head Dimension: 128
          
      -   Gated Attention:    -   Number of Attention Heads: 8 for Q and 2 for KV
              -   Head Dimension: 256
              -   Rotary Position Embedding Dimension: 64
          
      -   Feed Forward Network:    -   Intermediate Dimension: 3584
          
      -   LM Output: 248320 (Tied to token embedding)
      -   MTP: trained with multi-steps
    
-   Context Length: 262,144 natively

## Quickstart

> \[!Important\] Qwen3.5 models support both non-thinking and thinking mode. **Qwen3.5-0.8B operates in non-thinking mode by default**. To enable thinking, refer to the examples [here](#thinking-mode).

For streamlined integration, we recommend using Qwen3.5 via APIs. Below is a guide to use Qwen3.5 via OpenAI-compatible API.

### Serving Qwen3.5

Qwen3.5 can be served via APIs with popular inference frameworks. In the following, we show example commands to launch OpenAI-Compatible API servers for Qwen3.5 models.

> \[!Important\] Inference efficiency and throughput vary significantly across frameworks. We recommend using the latest framework versions to ensure optimal performance and compatibility. For production workloads or high-throughput scenarios, dedicated serving engines such as SGLang, KTransformers or vLLM are strongly recommended.

> \[!Important\] The model has a default context length of 262,144 tokens. If you encounter out-of-memory (OOM) errors, consider reducing the context window.

#### SGLang

[SGLang](https://github.com/sgl-project/sglang) is a fast serving framework for large language models and vision language models. SGLang from the main branch of the open-source repository is required for Qwen3.5, which can be installed using the following command in a fresh environment:

```
uv pip install 'git+https://github.com/sgl-project/sglang.git#subdirectory=python&egg=sglang[all]'

copy


```

See [its documentation](https://docs.sglang.ai/get_started/install.html) for more details.

The following will create API endpoints at 
```
http://localhost:8000/v1
```
:

-   **Standard Version**: The following command can be used to create an API endpoint with maximum context length 262,144 tokens using tensor parallel on 8 GPUs.
    
    ```
    python -m sglang.launch_server --model-path Qwen/Qwen3.5-0.8B --port 8000 --tp-size 1 --mem-fraction-static 0.8 --context-length 262144
    
    copy
    
    
    ```
    
-   **Tool Use**: To support tool use, you can use the following command.
    
    ```
    python -m sglang.launch_server --model-path Qwen/Qwen3.5-0.8B --port 8000 --tp-size 1 --mem-fraction-static 0.8 --context-length 262144 --tool-call-parser qwen3_coder
    
    copy
    
    
    ```
    
-   **Multi-Token Prediction (MTP)**: The following command is recommended for MTP:
    
    ```
    python -m sglang.launch_server --model-path Qwen/Qwen3.5-0.8B --port 8000 --tp-size 1 --mem-fraction-static 0.8 --context-length 262144 --speculative-algo NEXTN --speculative-num-steps 3 --speculative-eagle-topk 1 --speculative-num-draft-tokens 4
    
    copy
    
    
    ```

#### vLLM

[vLLM](https://github.com/vllm-project/vllm) is a high-throughput and memory-efficient inference and serving engine for LLMs. vLLM from the main branch of the open-source repository is required for Qwen3.5, which can be installed using the following command in a fresh environment:

```
uv pip install vllm --torch-backend=auto --extra-index-url https://wheels.vllm.ai/nightly

copy


```

See [its documentation](https://docs.vllm.ai/en/stable/getting_started/installation/index.html) for more details.

For detailed Qwen3.5 usage guide, see the [vLLM Qwen3.5 recipe](https://docs.vllm.ai/projects/recipes/en/latest/Qwen/Qwen3.5.html).

The following will create API endpoints at 
```
http://localhost:8000/v1
```
:

-   **Standard Version**: The following command can be used to create an API endpoint with maximum context length 262,144 tokens using tensor parallel on 8 GPUs.
    
    ```
    vllm serve Qwen/Qwen3.5-0.8B --port 8000 --tensor-parallel-size 1 --max-model-len 262144 
    
    copy
    
    
    ```
    
-   **Tool Call**: To support tool use, you can use the following command.
    
    ```
    vllm serve Qwen/Qwen3.5-0.8B --port 8000 --tensor-parallel-size 1 --max-model-len 262144 --enable-auto-tool-choice --tool-call-parser qwen3_coder 
    
    copy
    
    
    ```
    
-   **Multi-Token Prediction (MTP)**: The following command is recommended for MTP:
    
    ```
    vllm serve Qwen/Qwen3.5-0.8B --port 8000 --tensor-parallel-size 1 --max-model-len 262144 --speculative-config '{"method":"qwen3_next_mtp","num_speculative_tokens":2}'
    
    copy
    
    
    ```
    
-   **Text-Only**: The following command skips the vision encoder and multimodal profiling to free up memory for additional KV cache:
    
    ```
    vllm serve Qwen/Qwen3.5-0.8B --port 8000 --tensor-parallel-size 1 --max-model-len 262144 --language-model-only
    
    copy
    
    
    ```

#### KTransformers

[KTransformers](https://github.com/kvcache-ai/ktransformers) is a flexible framework for experiencing cutting-edge LLM inference optimizations with CPU-GPU heterogeneous computing. For running Qwen3.5 with KTransformers, see the [KTransformers Deployment Guide](https://github.com/kvcache-ai/ktransformers/blob/main/doc/en/Qwen3.5.md).

#### Hugging Face Transformers

Hugging Face Transformers contains a _lightweight_ server which can be used for quick testing and moderate load deployment. The latest 
```
transformers
```
 is required for Qwen3.5:

```
pip install "transformers[serving] @ git+https://github.com/huggingface/transformers.git@main"

copy


```

See [its documentation](https://huggingface.co/docs/transformers/main/serving) for more details. Please also make sure torchvision and pillow are installed.

Then, run 
```
transformers serve
```
 to launch a server with API endpoints at 
```
http://localhost:8000/v1
```
; it will place the model on accelerators if available:

```
transformers serve --force-model Qwen/Qwen3.5-0.8B --port 8000 --continuous-batching

copy


```

### Using Qwen3.5 via the Chat Completions API

The chat completions API is accessible via standard HTTP requests or OpenAI SDKs. Here, we show examples using the OpenAI Python SDK.

Before starting, make sure it is installed and the API key and the API base URL is configured, e.g.:

```
pip install -U openai
# Set the following accordingly
export OPENAI_BASE_URL="http://localhost:8000/v1"
export OPENAI_API_KEY="EMPTY"

copy


```

> \[!Tip\] We recommend using the following set of sampling parameters for generation
> 
> -   Non-thinking mode for text tasks: 
>     ```
>     temperature=1.0, top_p=1.00, top_k=20, min_p=0.0, presence_penalty=2.0, repetition_penalty=1.0
>     ```
>     
> -   Non-thinking mode for VL tasks: 
>     ```
>     temperature=0.7, top_p=0.80, top_k=20, min_p=0.0, presence_penalty=1.5, repetition_penalty=1.0
>     ```
>     
> -   Thinking mode for text tasks: 
>     ```
>     temperature=1.0, top_p=0.95, top_k=20, min_p=0.0, presence_penalty=1.5, repetition_penalty=1.0
>     ```
>     
> -   Thinking mode for VL or precise coding (e.g. WebDev) tasks : 
>     ```
>     temperature=0.6, top_p=0.95, top_k=20, min_p=0.0, presence_penalty=0.0, repetition_penalty=1.0
>     ```
> 
> Please note that the support for sampling parameters varies according to inference frameworks.

#### Text-Only Input

```
from openai import OpenAI
# Configured by environment variables
client = OpenAI()

messages = [
    {"role": "user", "content": "Give me a short introduction to large language models."},
]

chat_response = client.chat.completions.create(
    model="Qwen/Qwen3.5-0.8B",
    messages=messages,
    max_tokens=32768,
    temperature=1.0,
    top_p=1.0,
    presence_penalty=2.0,
    extra_body={
        "top_k": 20,
    }, 
)
print("Chat response:", chat_response)

copy


```

#### Image Input

```
from openai import OpenAI
# Configured by environment variables
client = OpenAI()

messages = [
    {
        "role": "user",
        "content": [
            {
                "type": "image_url",
                "image_url": {
                    "url": "https://qianwen-res.oss-accelerate.aliyuncs.com/Qwen3.5/demo/RealWorld/RealWorld-04.png"
                }
            },
            {
                "type": "text",
                "text": "Where is this?"
            }
        ]
    }
]

chat_response = client.chat.completions.create(
    model="Qwen/Qwen3.5-0.8B",
    messages=messages,
    max_tokens=32768,
    temperature=0.7,
    top_p=0.8,
    presence_penalty=1.5,
    extra_body={
        "top_k": 20,
    }, 
)
print("Chat response:", chat_response)

copy


```

#### Video Input

```
from openai import OpenAI
# Configured by environment variables
client = OpenAI()

messages = [
    {
        "role": "user",
        "content": [
            {
                "type": "video_url",
                "video_url": {
                    "url": "https://qianwen-res.oss-accelerate.aliyuncs.com/Qwen3.5/demo/video/N1cdUjctpG8.mp4"
                }
            },
            {
                "type": "text",
                "text": "Summarize the video content."
            }
        ]
    }
]

# When vLLM is launched with `--media-io-kwargs '{"video": {"num_frames": -1}}'`,
# video frame sampling can be configured via `extra_body` (e.g., by setting `fps`).
# This feature is currently supported only in vLLM.
#
# By default, `fps=2` and `do_sample_frames=True`.
# With `do_sample_frames=True`, you can customize the `fps` value to set your desired video sampling rate.
chat_response = client.chat.completions.create(
    model="Qwen/Qwen3.5-0.8B",
    messages=messages,
    max_tokens=32768,
    temperature=0.7,
    top_p=0.8,
    presence_penalty=1.5,
    extra_body={
        "top_k": 20,
        "mm_processor_kwargs": {"fps": 2, "do_sample_frames": True},
    }, 
)

print("Chat response:", chat_response)

copy


```

#### Thinking Mode

> \[!Important\] Qwen3.5 does not officially support the soft switch of Qwen3, i.e., 
> ```
> /think
> ```
>  and 
> ```
> /nothink
> ```
> .

You can make the model think before response by configuring the API parameters. For example,

```
from openai import OpenAI
# Configured by environment variables
client = OpenAI()

messages = [
    {"role": "user", "content": "Type \"I love Qwen3.5\" backwards"},
]

chat_response = client.chat.completions.create(
    model="Qwen/Qwen3.5-0.8B",
    messages=messages,
    max_tokens=81920,
    temperature=1.0,
    top_p=0.95,
    presence_penalty=1.5,
    extra_body={
        "top_k": 20,
        "enable_thinking": True,
    }, 
)
print("Chat response:", chat_response)

copy


```

> \[!Important\] In thinking mode, we have observed that when using the recommended sampling parameters, Qwen3.5-0.8B is more prone to entering thinking loops compared to other Qwen3.5 models, which may prevent it from terminating generation properly. We recommend further tuning the sampling parameters specific to your use case and utilizing the API's streaming generation mode (if supported) to enable timely detection and interruption of such anomalous generation behaviors.

## Agentic Usage

Qwen3.5 excels in tool calling capabilities.

### Qwen-Agent

We recommend using [Qwen-Agent](https://github.com/QwenLM/Qwen-Agent) to quickly build Agent applications with Qwen3.5.

To define the available tools, you can use the MCP configuration file, use the integrated tool of Qwen-Agent, or integrate other tools by yourself.

```
import os
from qwen_agent.agents import Assistant

# Define LLM
# Using OpenAI-compatible API endpoint. The API backend should disable response parsers.
llm_cfg = {
    # Use your own model service compatible with OpenAI API by vLLM/SGLang:
    'model': 'Qwen/Qwen3.5-0.8B',
    'model_type': 'qwenvl_oai',
    'model_server': 'http://localhost:8000/v1',  # api_base
    'api_key': 'EMPTY',

    'generate_cfg': {
        'use_raw_api': True,  
        # Pass the parameter of whether to enable thinking mode in this way
        # 'extra_body': {
        #    'chat_template_kwargs': {'enable_thinking': True}
        # },
    },
}

# Define Tools
tools = [
    {'mcpServers': {  # You can specify the MCP configuration file
            "filesystem": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", "/Users/xxxx/Desktop"]
            }
        }
    }
]

# Define Agent
bot = Assistant(llm=llm_cfg, function_list=tools)

# Streaming generation
messages = [{'role': 'user', 'content': 'Help me organize my desktop.'}]
for responses in bot.run(messages=messages):
    pass
print(responses)

# Streaming generation
messages = [{'role': 'user', 'content': 'Develop a dog website and save it on the desktop'}]
for responses in bot.run(messages=messages):
    pass
print(responses)

copy


```

### Qwen Code

[Qwen Code](https://github.com/QwenLM/qwen-code) is an open-source AI agent for the terminal, optimized for Qwen models. It helps you understand large codebases, automate tedious work, and ship faster.

For more information, please refer to [Qwen Code](https://qwenlm.github.io/qwen-code-docs/).

## Best Practices

To achieve optimal performance, we recommend the following settings:

1.  **Sampling Parameters**:
    
      3.   We suggest using the following sets of sampling parameters depending on the mode and task type:
          
              5.   **Non-thinking mode for text tasks**:  
                  ```
                  temperature=1.0
                  ```
                  , 
                  ```
                  top_p=1.00
                  ```
                  , 
                  ```
                  top_k=20
                  ```
                  , 
                  ```
                  min_p=0.0
                  ```
                  , 
                  ```
                  presence_penalty=2.0
                  ```
                  , 
                  ```
                  repetition_penalty=1.0
                  ```
                  
              30.   **Non-thinking mode for VL tasks**:  
                  ```
                  temperature=0.7
                  ```
                  , 
                  ```
                  top_p=0.80
                  ```
                  , 
                  ```
                  top_k=20
                  ```
                  , 
                  ```
                  min_p=0.0
                  ```
                  , 
                  ```
                  presence_penalty=1.5
                  ```
                  , 
                  ```
                  repetition_penalty=1.0
                  ```
                  
              55.   **Thinking mode for text tasks**:  
                  ```
                  temperature=1.0
                  ```
                  , 
                  ```
                  top_p=0.95
                  ```
                  , 
                  ```
                  top_k=20
                  ```
                  , 
                  ```
                  min_p=0.0
                  ```
                  , 
                  ```
                  presence_penalty=1.5
                  ```
                  , 
                  ```
                  repetition_penalty=1.0
                  ```
                  
              80.   **Thinking mode for VL or precise coding (e.g., WebDev) tasks**:  
                  ```
                  temperature=0.6
                  ```
                  , 
                  ```
                  top_p=0.95
                  ```
                  , 
                  ```
                  top_k=20
                  ```
                  , 
                  ```
                  min_p=0.0
                  ```
                  , 
                  ```
                  presence_penalty=0.0
                  ```
                  , 
                  ```
                  repetition_penalty=1.0
                  ```
          
      105.   For supported frameworks, you can adjust the 
          ```
          presence_penalty
          ```
           parameter between 0 and 2 to reduce endless repetitions. However, using a higher value may occasionally result in language mixing and a slight decrease in model performance.
    
2.  **Adequate Output Length**: We recommend using an output length of 32,768 tokens for most queries. For benchmarking on highly complex problems, such as those found in math and programming competitions, we suggest setting the max output length to 81,920 tokens. This provides the model with sufficient space to generate detailed and comprehensive responses, thereby enhancing its overall performance.
    
3.  **Standardize Output Format**: We recommend using prompts to standardize model outputs when benchmarking.
    
      115.   **Math Problems**: Include "Please reason step by step, and put your final answer within \\boxed{}." in the prompt.
      116.   **Multiple-Choice Questions**: Add the following JSON structure to the prompt to standardize responses: "Please show your choice in the 
          ```
          answer
          ```
           field with only the choice letter, e.g., 
          ```
          "answer": "C"
          ```
          ."
    
4.  **No Thinking Content in History**: In multi-turn conversations, the historical model output should only include the final output part and does not need to include the thinking content. It is implemented in the provided chat template in Jinja2. However, for frameworks that do not directly use the Jinja2 chat template, it is up to the developers to ensure that the best practice is followed.
    
5.  **Long Video Understanding**: To optimize inference efficiency for plain text and images, the 
    ```
    size
    ```
     parameter in the released 
    ```
    video_preprocessor_config.json
    ```
     is conservatively configured. It is recommended to set the 
    ```
    longest_edge
    ```
     parameter in the video\_preprocessor\_config file to 469,762,048 (corresponding to 224k video tokens) to enable higher frame-rate sampling for hour-scale videos and thereby achieve superior performance. For example,
    
    ```
    {"longest_edge": 469762048, "shortest_edge": 4096}
    
    copy
    
    
    ```
    
    Alternatively, override the default values via engine startup parameters. For implementation details, refer to: [vLLM](https://github.com/vllm-project/vllm/pull/34330) / [SGLang](https://github.com/sgl-project/sglang/pull/18467).

### Citation

If you find our work helpful, feel free to give us a cite.

```
@misc{qwen3.5,
    title  = {{Qwen3.5}: Towards Native Multimodal Agents},
    author = {{Qwen Team}},
    month  = {February},
    year   = {2026},
    url    = {https://qwen.ai/blog?id=qwen3.5}
}

copy


```