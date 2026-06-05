#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Quick Qwen3 Model Test (CPU-compatible)

This script performs a rapid validation of Qwen3 models on CPU.
For full validation with GPU metrics, use p3_t01_qwen3_validation.py
with CUDA-enabled PyTorch.

Author: P3-T01 Task
"""

import sys
import torch
from pathlib import Path
from datetime import datetime
import json

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Model paths
EMBEDDING_MODEL_PATH = PROJECT_ROOT / "models" / "huggingface" / "Qwen3-Embedding-0.6B"
RERANKER_MODEL_PATH = PROJECT_ROOT / "models" / "huggingface" / "Qwen3-Reranker-0.6B"
OUTPUT_DIR = PROJECT_ROOT / "output" / "reports" / "qwen3_validation"


def print_header(title: str):
    """Print formatted header."""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def check_cuda():
    """Check CUDA availability."""
    print_header("Environment Check")
    print(f"PyTorch version: {torch.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"CUDA version: {torch.version.cuda}")
        print(f"GPU: {torch.cuda.get_device_name(0)}")
        print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
    else:
        print("⚠️  Running in CPU mode - inference will be slow")
        print("   Install CUDA PyTorch for GPU testing:")
        print("   pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118")
    return torch.cuda.is_available()


def verify_model_files(model_path: Path, model_name: str) -> dict:
    """Verify model files exist and are valid."""
    print_header(f"Verifying {model_name}")
    
    result = {
        "name": model_name,
        "path": str(model_path),
        "exists": model_path.exists(),
        "config_valid": False,
        "model_file_exists": False,
        "model_type": None,
        "total_size_mb": 0,
        "status": "FAIL"
    }
    
    if not model_path.exists():
        print(f"❌ Model path not found: {model_path}")
        return result
    
    # Check config.json
    config_path = model_path / "config.json"
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            result["config_valid"] = True
            result["model_type"] = config.get("model_type", "unknown")
            print(f"✓ config.json valid (model_type: {result['model_type']})")
        except Exception as e:
            print(f"✗ config.json error: {e}")
    else:
        print("✗ config.json not found")
    
    # Check model file
    model_file = model_path / "model.safetensors"
    if model_file.exists():
        result["model_file_exists"] = True
        result["model_size_mb"] = model_file.stat().st_size / (1024 ** 2)
        print(f"✓ model.safetensors found ({result['model_size_mb']:.1f} MB)")
    else:
        print("✗ model.safetensors not found")
    
    # Calculate total size
    total_size = sum(f.stat().st_size for f in model_path.rglob("*") if f.is_file())
    result["total_size_mb"] = total_size / (1024 ** 2)
    print(f"  Total size: {result['total_size_mb']:.1f} MB")
    
    if result["config_valid"] and result["model_file_exists"]:
        result["status"] = "PASS"
        print(f"✅ {model_name} verification PASSED")
    
    return result


def test_embedding_model(model_path: Path, device: str = "cpu") -> dict:
    """Test embedding model loading and basic inference."""
    print_header("Testing Embedding Model")
    
    result = {
        "model": "Qwen3-Embedding-0.6B",
        "device": device,
        "load_success": False,
        "inference_success": False,
        "embedding_dim": None,
        "load_time_s": None,
        "inference_time_s": None,
        "error": None
    }
    
    try:
        from transformers import AutoTokenizer, AutoModel
        import time
        
        print(f"Loading model on {device}...")
        start_time = time.perf_counter()
        
        tokenizer = AutoTokenizer.from_pretrained(
            str(model_path),
            trust_remote_code=True
        )
        
        model = AutoModel.from_pretrained(
            str(model_path),
            trust_remote_code=True
        ).to(device)
        model.eval()
        
        load_time = time.perf_counter() - start_time
        result["load_time_s"] = load_time
        result["load_success"] = True
        print(f"✓ Model loaded in {load_time:.2f}s")
        
        # Test inference with short text
        test_texts = ["紅樓夢是中國古典小說的巔峰之作"]
        
        print("Running inference test...")
        start_time = time.perf_counter()
        
        with torch.no_grad():
            encoded = tokenizer(
                test_texts,
                padding=True,
                truncation=True,
                max_length=128,  # Short for quick test
                return_tensors='pt'
            ).to(device)
            outputs = model(**encoded)
        
        inference_time = time.perf_counter() - start_time
        result["inference_time_s"] = inference_time
        
        # Get embedding
        if hasattr(outputs, 'last_hidden_state'):
            embeddings = outputs.last_hidden_state[:, 0, :]  # CLS token
            result["embedding_dim"] = embeddings.shape[-1]
            result["inference_success"] = True
            print(f"✓ Inference completed in {inference_time:.2f}s")
            print(f"  Embedding dimension: {result['embedding_dim']}")
        else:
            print(f"✗ Unexpected output format: {type(outputs)}")
        
        # Cleanup
        del model
        del tokenizer
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        
    except Exception as e:
        result["error"] = str(e)
        print(f"❌ Error: {e}")
    
    return result


def test_reranker_model(model_path: Path, device: str = "cpu") -> dict:
    """Test reranker model loading and basic inference."""
    print_header("Testing Reranker Model")
    
    result = {
        "model": "Qwen3-Reranker-0.6B",
        "device": device,
        "load_success": False,
        "inference_success": False,
        "load_time_s": None,
        "inference_time_s": None,
        "error": None
    }
    
    # Skip inference on CPU - too slow
    if device == "cpu":
        print("⚠️  Skipping reranker inference test on CPU (too slow)")
        print("   Reranker model will be tested on GPU")
        result["error"] = "CPU inference skipped - too slow"
        result["inference_success"] = None  # Mark as untested
        
        # Just test model loading
        try:
            from transformers import AutoTokenizer, AutoModelForSequenceClassification
            import time
            
            print(f"Loading model on {device}...")
            start_time = time.perf_counter()
            
            tokenizer = AutoTokenizer.from_pretrained(
                str(model_path),
                trust_remote_code=True
            )
            
            model = AutoModelForSequenceClassification.from_pretrained(
                str(model_path),
                trust_remote_code=True
            )
            # Don't move to device yet to save time
            
            load_time = time.perf_counter() - start_time
            result["load_time_s"] = load_time
            result["load_success"] = True
            print(f"✓ Model loaded in {load_time:.2f}s")
            print("  Inference test skipped on CPU")
            
            del model
            del tokenizer
            
        except Exception as e:
            result["error"] = str(e)
            print(f"❌ Error: {e}")
        
        return result
    
    try:
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        import time
        
        print(f"Loading model on {device}...")
        start_time = time.perf_counter()
        
        tokenizer = AutoTokenizer.from_pretrained(
            str(model_path),
            trust_remote_code=True
        )
        
        model = AutoModelForSequenceClassification.from_pretrained(
            str(model_path),
            trust_remote_code=True
        ).to(device)
        model.eval()
        
        load_time = time.perf_counter() - start_time
        result["load_time_s"] = load_time
        result["load_success"] = True
        print(f"✓ Model loaded in {load_time:.2f}s")
        
        # Test inference with query-passage pair
        query = "紅樓夢的作者是誰"
        passage = "紅樓夢是清代作家曹雪芹所著的一部長篇小說"
        
        print("Running inference test...")
        start_time = time.perf_counter()
        
        with torch.no_grad():
            encoded = tokenizer(
                query,
                passage,
                padding=True,
                truncation=True,
                max_length=128,
                return_tensors='pt'
            ).to(device)
            outputs = model(**encoded)
        
        inference_time = time.perf_counter() - start_time
        result["inference_time_s"] = inference_time
        
        # Get score
        if hasattr(outputs, 'logits'):
            logits = outputs.logits
            if logits.dim() == 2:
                # Multi-class or binary classification [batch, num_labels]
                score = logits.softmax(dim=-1)[0, -1].item()  # Get probability of positive class
            elif logits.numel() == 1:
                score = logits.item()
            else:
                score = logits[0].item()
            result["inference_success"] = True
            result["sample_score"] = score
            print(f"✓ Inference completed in {inference_time:.2f}s")
            print(f"  Logits shape: {logits.shape}")
            print(f"  Sample rerank score: {score:.4f}")
        else:
            print(f"✗ Unexpected output format: {type(outputs)}")
        
        # Cleanup
        del model
        del tokenizer
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        
    except Exception as e:
        result["error"] = str(e)
        print(f"❌ Error: {e}")
    
    return result


def save_quick_report(results: dict):
    """Save quick test report."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    report_path = OUTPUT_DIR / f"quick_test_{timestamp}.json"
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"\nReport saved to: {report_path}")
    return report_path


def main():
    """Run quick Qwen3 model test."""
    print("\n" + "=" * 60)
    print("  P3-T01: Quick Qwen3 Model Test")
    print("=" * 60)
    print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = {
        "timestamp": datetime.now().isoformat(),
        "cuda_available": False,
        "device": "cpu",
        "embedding_verification": None,
        "reranker_verification": None,
        "embedding_test": None,
        "reranker_test": None,
        "overall_status": "FAIL"
    }
    
    # Check environment
    cuda_available = check_cuda()
    results["cuda_available"] = cuda_available
    device = "cuda" if cuda_available else "cpu"
    results["device"] = device
    
    # Verify models
    results["embedding_verification"] = verify_model_files(EMBEDDING_MODEL_PATH, "Qwen3-Embedding-0.6B")
    results["reranker_verification"] = verify_model_files(RERANKER_MODEL_PATH, "Qwen3-Reranker-0.6B")
    
    # Test embedding model
    if results["embedding_verification"]["status"] == "PASS":
        results["embedding_test"] = test_embedding_model(EMBEDDING_MODEL_PATH, device)
    
    # Test reranker model
    if results["reranker_verification"]["status"] == "PASS":
        results["reranker_test"] = test_reranker_model(RERANKER_MODEL_PATH, device)
    
    # Determine overall status
    embedding_ok = (results["embedding_test"] and 
                   results["embedding_test"].get("inference_success", False))
    reranker_ok = (results["reranker_test"] and 
                  results["reranker_test"].get("inference_success", False))
    
    if embedding_ok and reranker_ok:
        results["overall_status"] = "PASS"
    elif embedding_ok or reranker_ok:
        results["overall_status"] = "PARTIAL"
    
    # Print summary
    print_header("Test Summary")
    print(f"Device: {device}")
    print(f"Embedding Model: {'✅ PASS' if embedding_ok else '❌ FAIL'}")
    print(f"Reranker Model: {'✅ PASS' if reranker_ok else '❌ FAIL'}")
    print(f"Overall Status: {results['overall_status']}")
    
    if not cuda_available:
        print("\n⚠️  Note: This test ran on CPU. For full validation with VRAM")
        print("   metrics, install CUDA-enabled PyTorch and run:")
        print("   python scripts/rag/indexing/p3_t01_qwen3_validation.py")
    
    # Save report
    save_quick_report(results)
    
    return 0 if results["overall_status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
