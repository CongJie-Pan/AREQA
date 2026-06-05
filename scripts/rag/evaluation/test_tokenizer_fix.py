"""
Simple test to verify Qwen3-Reranker tokenizer padding fix.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RERANKER_MODEL_PATH = PROJECT_ROOT / "models" / "huggingface" / "Qwen3-Reranker-0.6B"

print("=" * 70)
print("TESTING QWEN3-RERANKER TOKENIZER PADDING FIX")
print("=" * 70)

try:
    from transformers import AutoTokenizer
    
    print("\n1. Loading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(
        RERANKER_MODEL_PATH, 
        trust_remote_code=True
    )
    print(f"   ✅ Tokenizer loaded")
    print(f"   pad_token BEFORE fix: {tokenizer.pad_token}")
    print(f"   pad_token_id BEFORE fix: {tokenizer.pad_token_id}")
    
    # Apply fix
    print("\n2. Applying padding token fix...")
    if tokenizer.pad_token is None:
        if tokenizer.eos_token is not None:
            tokenizer.pad_token = tokenizer.eos_token
            print(f"   ✅ Set pad_token = eos_token ('{tokenizer.eos_token}')")
        else:
            special_tokens = tokenizer.all_special_tokens
            if special_tokens:
                tokenizer.pad_token = special_tokens[0]
                print(f"   ✅ Set pad_token = first special token ('{special_tokens[0]}')")
            else:
                tokenizer.add_special_tokens({'pad_token': '[PAD]'})
                print(f"   ✅ Added new [PAD] token")
    
    print(f"\n   pad_token AFTER fix: {tokenizer.pad_token}")
    print(f"   pad_token_id AFTER fix: {tokenizer.pad_token_id}")
    
    if tokenizer.pad_token_id is None:
        print("\n   ❌ FAILED: pad_token_id is still None!")
        sys.exit(1)
    
    # Test batch tokenization
    print("\n3. Testing batch tokenization...")
    test_pairs = [
        ["什麼是紅樓夢？", "《紅樓夢》是中國古典四大名著之一"],
        ["賈寶玉是誰？", "賈寶玉是《紅樓夢》的主角"]
    ]
    
    inputs = tokenizer(
        test_pairs,
        padding=True,
        truncation=True,
        max_length=512,
        return_tensors="pt"
    )
    
    print(f"   ✅ Batch tokenization successful!")
    print(f"   Input shape: {inputs['input_ids'].shape}")
    print(f"   Padding used: {(inputs['input_ids'] == tokenizer.pad_token_id).sum().item()} tokens")
    
    print("\n" + "=" * 70)
    print("✅ ALL TESTS PASSED!")
    print("=" * 70)
    print("The tokenizer padding fix is working correctly.")
    print("The BM25 evaluation should now work without errors.")
    print("=" * 70)

except Exception as e:
    print(f"\n❌ ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
