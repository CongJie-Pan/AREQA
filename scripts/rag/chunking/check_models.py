#!/usr/bin/env python
"""測試 OpenRouter API 調用 - 測試不同模型格式"""

import os
import sys
from pathlib import Path

# 添加 project root
PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

# 加載環境變數
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

def test_model_format():
    """測試不同的模型名稱格式"""
    import litellm
    
    api_key = os.environ.get('OPENROUTER_API_KEY')
    if not api_key:
        print("Error: OPENROUTER_API_KEY not set")
        return
    
    print(f"API Key found: {api_key[:8]}...{api_key[-4:]}")
    
    # 測試 prompt
    test_prompt = "請用一句話解釋什麼是「論語」。"
    
    # 測試不同的模型
    test_models = [
        "openrouter/moonshotai/kimi-k2.5",
        "openrouter/moonshotai/kimi-k2",
        "openrouter/moonshotai/kimi-k2-0905",
    ]
    
    for model_name in test_models:
        print(f"\n{'='*60}")
        print(f"Testing: {model_name}")
        print(f"Prompt: {test_prompt}")
        print('='*60)
        
        try:
            response = litellm.completion(
                model=model_name,
                messages=[{"role": "user", "content": test_prompt}],
                api_key=api_key,
                max_tokens=200,
            )
            content = response.choices[0].message.content
            print(f"✅ SUCCESS!")
            print(f"Response length: {len(content)} chars")
            print(f"Response: {content}")
            
        except Exception as e:
            print(f"❌ FAILED: {str(e)[:300]}")

if __name__ == "__main__":
    test_model_format()
