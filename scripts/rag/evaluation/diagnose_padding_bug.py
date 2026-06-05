#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diagnostic Test for Padding Token Bug

This script diagnoses why "Cannot handle batch sizes > 1 if no padding token is defined"
error persists even after setting tokenizer.pad_token_id.

Hypotheses:
===========
H1: model.config.pad_token_id is not set (model checks config, not tokenizer)
H2: Qwen3-Reranker has custom embedding layer with special requirements
H3: trust_remote_code loads custom code with its own checks
H4: File not properly saved/loaded

Author: ML Engineer
Date: 2026-02-02
"""

import sys
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

RERANKER_MODEL_PATH = PROJECT_ROOT / "models" / "huggingface" / "Qwen3-Reranker-0.6B"


def diagnose_padding_token():
    """
    Comprehensive diagnosis of padding token configuration.
    
    This function checks all possible locations where pad_token_id might need to be set.
    """
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    
    print("=" * 80)
    print("PADDING TOKEN DIAGNOSTIC TEST")
    print("=" * 80)
    
    # ========================================================================
    # Step 1: Load Tokenizer and check initial state
    # ========================================================================
    print("\n[STEP 1] Loading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(
        RERANKER_MODEL_PATH, 
        trust_remote_code=True
    )
    
    print(f"\n📋 TOKENIZER INITIAL STATE:")
    print(f"   pad_token:     {tokenizer.pad_token!r}")
    print(f"   pad_token_id:  {tokenizer.pad_token_id}")
    print(f"   eos_token:     {tokenizer.eos_token!r}")
    print(f"   eos_token_id:  {tokenizer.eos_token_id}")
    print(f"   bos_token:     {tokenizer.bos_token!r}")
    print(f"   bos_token_id:  {tokenizer.bos_token_id}")
    print(f"   unk_token:     {tokenizer.unk_token!r}")
    print(f"   unk_token_id:  {tokenizer.unk_token_id}")
    print(f"   all_special_tokens: {tokenizer.all_special_tokens}")
    print(f"   all_special_ids:    {tokenizer.all_special_ids}")
    
    # ========================================================================
    # Step 2: Apply fix to tokenizer
    # ========================================================================
    print("\n[STEP 2] Applying padding token fix to tokenizer...")
    
    if tokenizer.pad_token is None:
        if tokenizer.eos_token is not None:
            tokenizer.pad_token = tokenizer.eos_token
            tokenizer.pad_token_id = tokenizer.eos_token_id
            print(f"   ✅ Set pad_token = eos_token: {tokenizer.pad_token!r}")
        else:
            tokenizer.add_special_tokens({'pad_token': '[PAD]'})
            print(f"   ✅ Added new [PAD] token")
    
    tokenizer.padding_side = 'right'
    
    print(f"\n📋 TOKENIZER AFTER FIX:")
    print(f"   pad_token:     {tokenizer.pad_token!r}")
    print(f"   pad_token_id:  {tokenizer.pad_token_id}")
    print(f"   padding_side:  {tokenizer.padding_side}")
    
    # ========================================================================
    # Step 3: Load Model and check config
    # ========================================================================
    print("\n[STEP 3] Loading model...")
    model = AutoModelForSequenceClassification.from_pretrained(
        RERANKER_MODEL_PATH,
        trust_remote_code=True,
        torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32
    )
    
    print(f"\n📋 MODEL CONFIG (BEFORE FIX):")
    print(f"   config.pad_token_id:  {model.config.pad_token_id}")
    print(f"   config.eos_token_id:  {model.config.eos_token_id}")
    print(f"   config.bos_token_id:  {model.config.bos_token_id}")
    print(f"   config.vocab_size:    {model.config.vocab_size}")
    
    # ========================================================================
    # Step 4: Check model architecture for embedding layer
    # ========================================================================
    print("\n[STEP 4] Checking model architecture...")
    print(f"   Model type: {type(model).__name__}")
    print(f"   Model class: {model.__class__.__module__}.{model.__class__.__name__}")
    
    # Find embedding layer
    for name, module in model.named_modules():
        if 'embed' in name.lower():
            print(f"   Found embedding: {name} -> {type(module).__name__}")
    
    # ========================================================================
    # Step 5: THE KEY FIX - Set pad_token_id on model.config
    # ========================================================================
    print("\n[STEP 5] 🔧 APPLYING CRITICAL FIX: Setting model.config.pad_token_id...")
    
    # THIS IS THE CRITICAL FIX!
    if model.config.pad_token_id is None:
        model.config.pad_token_id = tokenizer.pad_token_id
        print(f"   ✅ Set model.config.pad_token_id = {model.config.pad_token_id}")
    
    print(f"\n📋 MODEL CONFIG (AFTER FIX):")
    print(f"   config.pad_token_id:  {model.config.pad_token_id}")
    
    # ========================================================================
    # Step 6: Test tokenization with batch
    # ========================================================================
    print("\n[STEP 6] Testing tokenization with batch...")
    
    test_pairs = [
        ["胥斯原 庶繁", "這是一段測試文本"],
        ["賈寶玉", "賈寶玉是紅樓夢的主角"]
    ]
    
    try:
        inputs = tokenizer(
            test_pairs,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt"
        )
        print(f"   ✅ Tokenization successful!")
        print(f"      input_ids shape: {inputs['input_ids'].shape}")
        print(f"      attention_mask shape: {inputs['attention_mask'].shape}")
    except Exception as e:
        print(f"   ❌ Tokenization failed: {e}")
        return False
    
    # ========================================================================
    # Step 7: Test model forward pass
    # ========================================================================
    print("\n[STEP 7] Testing model forward pass...")
    
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    model = model.to(device)
    model.eval()
    inputs = inputs.to(device)
    
    try:
        with torch.no_grad():
            outputs = model(**inputs)
        print(f"   ✅ Model forward pass successful!")
        print(f"      Output logits shape: {outputs.logits.shape}")
        print(f"      Output scores: {outputs.logits.squeeze(-1).cpu().numpy()}")
        return True
    except ValueError as e:
        if "padding token" in str(e).lower():
            print(f"   ❌ PADDING TOKEN ERROR: {e}")
            print("\n   🔍 DIAGNOSIS: The error comes from model's internal embedding layer.")
            print("   The embedding layer checks model.config.pad_token_id, not tokenizer.pad_token_id!")
            
            # Additional diagnosis
            print("\n   📋 Checking embedding layer config...")
            if hasattr(model, 'get_input_embeddings'):
                emb = model.get_input_embeddings()
                print(f"      Embedding type: {type(emb).__name__}")
                if hasattr(emb, 'padding_idx'):
                    print(f"      Embedding padding_idx: {emb.padding_idx}")
        else:
            print(f"   ❌ Other error: {e}")
        return False
    except Exception as e:
        print(f"   ❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_with_full_fix():
    """
    Test with the complete fix including model.config.pad_token_id.
    """
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    
    print("\n" + "=" * 80)
    print("TESTING WITH COMPLETE FIX")
    print("=" * 80)
    
    # Load tokenizer
    tokenizer = AutoTokenizer.from_pretrained(
        RERANKER_MODEL_PATH, 
        trust_remote_code=True
    )
    
    # Fix tokenizer
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
        tokenizer.pad_token_id = tokenizer.eos_token_id
    tokenizer.padding_side = 'right'
    
    # Load model
    model = AutoModelForSequenceClassification.from_pretrained(
        RERANKER_MODEL_PATH,
        trust_remote_code=True,
        torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
        # KEY FIX: Set pad_token_id in from_pretrained
        pad_token_id=tokenizer.pad_token_id
    )
    
    # Double-check config
    print(f"\n📋 After from_pretrained with pad_token_id:")
    print(f"   model.config.pad_token_id: {model.config.pad_token_id}")
    
    # If still None, force set it
    if model.config.pad_token_id is None:
        model.config.pad_token_id = tokenizer.pad_token_id
        print(f"   Force set model.config.pad_token_id = {model.config.pad_token_id}")
    
    # Test
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    model = model.to(device)
    model.eval()
    
    test_pairs = [
        ["胥斯原 庶繁", "這是一段測試文本用於詩經相關內容"],
        ["賈寶玉 林黛玉", "賈寶玉是紅樓夢的主角與林黛玉是表兄妹"]
    ]
    
    inputs = tokenizer(
        test_pairs,
        padding=True,
        truncation=True,
        max_length=512,
        return_tensors="pt"
    ).to(device)
    
    try:
        with torch.no_grad():
            outputs = model(**inputs)
        print(f"\n✅ COMPLETE FIX WORKS!")
        print(f"   Scores: {outputs.logits.squeeze(-1).cpu().numpy()}")
        return True
    except Exception as e:
        print(f"\n❌ Still failing: {e}")
        return False


if __name__ == "__main__":
    print("\n" + "🔍" * 40)
    print("   PADDING TOKEN BUG DIAGNOSTIC TOOL")
    print("🔍" * 40)
    
    # Run diagnosis
    success1 = diagnose_padding_token()
    
    # Run with complete fix
    success2 = test_with_full_fix()
    
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"   Diagnosis test:     {'✅ PASSED' if success1 else '❌ FAILED'}")
    print(f"   Complete fix test:  {'✅ PASSED' if success2 else '❌ FAILED'}")
    
    if not success1 and success2:
        print("\n🎯 ROOT CAUSE CONFIRMED:")
        print("   The issue is that model.config.pad_token_id was not set.")
        print("   The fix is to pass pad_token_id to from_pretrained() or")
        print("   set model.config.pad_token_id after loading.")
    
    print("=" * 80)
