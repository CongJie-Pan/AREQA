#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quick test script to verify Reranker tokenizer padding token configuration.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from transformers import AutoTokenizer

RERANKER_MODEL_PATH = PROJECT_ROOT / "models" / "huggingface" / "Qwen3-Reranker-0.6B"

print("=" * 70)
print("Testing Qwen3-Reranker Tokenizer Padding Token Configuration")
print("=" * 70)

# Load tokenizer
print(f"\n1. Loading tokenizer from: {RERANKER_MODEL_PATH}")
tokenizer = AutoTokenizer.from_pretrained(
    RERANKER_MODEL_PATH, 
    trust_remote_code=True
)

# Check initial state
print(f"\n2. Initial state:")
print(f"   - pad_token: {tokenizer.pad_token}")
print(f"   - pad_token_id: {tokenizer.pad_token_id}")
print(f"   - eos_token: {tokenizer.eos_token}")
print(f"   - eos_token_id: {tokenizer.eos_token_id}")
print(f"   - all_special_tokens: {tokenizer.all_special_tokens}")

# Apply fix
print(f"\n3. Applying padding token fix...")
if tokenizer.pad_token is None:
    if tokenizer.eos_token is not None:
        tokenizer.pad_token = tokenizer.eos_token
        print(f"   ✅ Set pad_token to eos_token: '{tokenizer.eos_token}'")
    else:
        special_tokens = tokenizer.all_special_tokens
        if special_tokens:
            tokenizer.pad_token = special_tokens[0]
            print(f"   ✅ Set pad_token to first special token: '{special_tokens[0]}'")
        else:
            tokenizer.add_special_tokens({'pad_token': '[PAD]'})
            print(f"   ✅ Added custom [PAD] token")

# Verify final state
print(f"\n4. Final state:")
print(f"   - pad_token: {tokenizer.pad_token}")
print(f"   - pad_token_id: {tokenizer.pad_token_id}")

# Test batch tokenization
print(f"\n5. Testing batch tokenization...")
test_pairs = [
    ["什麼是紅樓夢？", "《紅樓夢》是清代作家曹雪芹創作的章回體長篇小說。"],
    ["賈寶玉是誰？", "賈寶玉是《紅樓夢》的男主角。"]
]

try:
    inputs = tokenizer(
        test_pairs,
        padding=True,
        truncation=True,
        max_length=512,
        return_tensors="pt"
    )
    print(f"   ✅ Batch tokenization successful!")
    print(f"   - Input shape: {inputs['input_ids'].shape}")
    print(f"   - Attention mask shape: {inputs['attention_mask'].shape}")
except Exception as e:
    print(f"   ❌ Batch tokenization failed: {e}")
    sys.exit(1)

print(f"\n" + "=" * 70)
print("✅ All tests passed! Padding token is correctly configured.")
print("=" * 70)
