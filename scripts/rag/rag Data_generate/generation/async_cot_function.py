# Add this after validate_reasoning function (around line 360)

async def generate_cot_samples_async(
    candidates: List[Dict[str, Any]],
    config: Dict[str, Any],
    target_count: int,
    max_concurrent: int = 6
) -> Tuple[List[CoTResult], Dict[str, Any]]:
    """Async concurrent version of CoT generation for 5-10x speed improvement.
    
    Why async:
    - Process 5-8 requests in parallel
    - 5-10x speed improvement
    - Reduces 1500 samples from 4-5 hours to 30-50 minutes
    
    Args:
        candidates: List of candidate dictionaries
        config: Generation configuration
        target_count: Target number of successful generations
        max_concurrent: Max concurrent API requests (default: 6)
    
    Returns:
        Tuple of (results, stats)
    """
    # Check API key
    if DOTENV_AVAILABLE:
        console.print("[dim]✅ 已從 .env 載入環境變數[/dim]")
    
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        console.print("[red]❌ OPENROUTER_API_KEY 環境變數未設定[/red]")
        console.print("[yellow]請確認 .env 檔案包含: OPENROUTER_API_KEY=your_key[/yellow]")
        return [], {"error": "no_api_key"}
    
    results: List[CoTResult] = []
    results_lock = asyncio.Lock()  # Thread-safe results list
    stats = {
        "total_candidates": len(candidates),
        "target_count": target_count,
        "success_count": 0,
        "warning_count": 0,
        "failure_count": 0,
        "retry_count": 0,
        "warning_types": {},
        "error_types": {},
        "avg_reasoning_length": 0,
        "avg_generation_time_ms": 0,
        "start_time": datetime.now().isoformat(),
    }
    stats_lock = asyncio.Lock()  # Thread-safe stats
    
    total_length = 0
    total_time = 0
    
    mode_text = "[yellow]🧪 測試模式[/yellow]" if TEST_MODE else "[green]📦 生產模式[/green]"
    console.print(Panel(
        f"[bold cyan]Phase 2: 生成 CoT 推理鏈 (並發模式)[/bold cyan]\n"
        f"模式: {mode_text}\n"
        f"目標數量: {target_count} 筆\n"
        f"候選數量: {len(candidates)} 筆\n"
        f"並發數: [bold]{max_concurrent}[/bold] 個同時請求",
        border_style="cyan"
    ))
    
    # Shuffle candidates for diversity
    random.shuffle(candidates)
    
    # Create semaphore for concurrency control
    semaphore = asyncio.Semaphore(max_concurrent)
    
    # Process candidates
    async def process_one(i, candidate):
        """Process single candidate with retries."""
        nonlocal total_length, total_time
        
        question = candidate.get("question", "")
        answer = candidate.get("original_answer", "")
        context = prepare_context(candidate, config["max_context_length"])
        
        # Generate with retries
        reasoning = None
        error_msg = None
        retries = 0
        start_time = time.time()
        
        for attempt in range(config["max_retries"]):
            reasoning, error_msg = await generate_cot_with_llm_async(
                question, answer, context, config, api_key, semaphore
            )
            
            if reasoning:
                break
            
            retries += 1
            async with stats_lock:
                stats["retry_count"] += 1
            await asyncio.sleep(0.5)  # Brief pause before retry
        
        generation_time = int((time.time() - start_time) * 1000)
        
        # Validate result
        result = None
        if reasoning:
            is_valid, warning = validate_reasoning(reasoning, config)
            
            if is_valid:
                result = CoTResult(
                    original_index=candidate.get("original_index", i),
                    question=question,
                    original_answer=answer,
                    context_used=context,
                    generated_reasoning=reasoning,
                    reasoning_length=len(reasoning),
                    generation_time_ms=generation_time,
                    success=True,
                    retry_count=retries,
                    metadata=candidate.get("metadata", {})
                )
                
                async with results_lock:
                    results.append(result)
                
                async with stats_lock:
                    stats["success_count"] += 1
                    total_length += len(reasoning)
                    total_time += generation_time
                    
                    if warning:
                        stats["warning_count"] += 1
                        stats["warning_types"][warning] = stats["warning_types"].get(warning, 0) + 1
            else:
                async with stats_lock:
                    stats["failure_count"] += 1
                    stats["error_types"][warning] = stats["error_types"].get(warning, 0) + 1
        else:
            async with stats_lock:
                stats["failure_count"] += 1
                if error_msg:
                    error_key = error_msg[:50]  # Truncate
                    stats["error_types"][error_key] = stats["error_types"].get(error_key, 0) + 1
        
        return result
    
    # Process in batches with progress bar
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console
    ) as progress:
        task = progress.add_task(
            f"[cyan]生成 CoT (已成功: 0/{target_count})...",
            total=min(len(candidates), target_count * 2)
        )
        
        # Process candidates in batches
        batch_size = max_concurrent
        for batch_start in range(0, len(candidates), batch_size):
            if stats["success_count"] >= target_count:
                console.print(f"\n[green]✅ 達到目標數量: {target_count}[/green]")
                break
            
            batch_end = min(batch_start + batch_size, len(candidates))
            batch = candidates[batch_start:batch_end]
            
            # Process batch concurrently
            tasks = [process_one(batch_start + j, candidate) for j, candidate in enumerate(batch)]
            await asyncio.gather(*tasks)
            
            progress.update(task, advance=len(batch), description=
                f"[cyan]生成 CoT (已成功: {stats['success_count']}/{target_count}, "
                f"失敗: {stats['failure_count']})..."
            )
            
            # Checkpoint every 50  successes
            if stats["success_count"] > 0 and stats["success_count"] % 50 == 0:
                save_checkpoint(results, stats)
    
    # Final stats
    if stats["success_count"] > 0:
        stats["avg_reasoning_length"] = total_length // stats["success_count"]
        stats["avg_generation_time_ms"] = total_time // stats["success_count"]
    
    stats["end_time"] = datetime.now().isoformat()
    
    return results, stats
