#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P3-T02: Query Expander (LiteLLM)
================================
使用 LLM (DeepSeek via OpenRouter) 將白話文問題擴展為古文關鍵詞。
這能解決「白話問古文」的語義鴻溝問題。

Requires:
    pip install litellm
    Environment variable: OPENROUTER_API_KEY
"""

import os
import logging
from typing import List
from rich.console import Console
from rich.panel import Panel

# Configure logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

console = Console()

class QueryExpander:
    """Expand simple queries into RAG-optimized keywords."""
    
    def __init__(self, model_name: str = "openrouter/deepseek/deepseek-chat"):
        """
        Initialize.
        Note: terminology might vary, "deepseek-v3.1-terminus" might map to a specific ID on OpenRouter.
        Using a standard DeepSeek ID for now, user can override.
        """
        self.model_name = model_name
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        
        if not self.api_key:
            console.print("[yellow]Warning: OPENROUTER_API_KEY not set. Query expansion will likely fail.[/yellow]")

    def expand(self, query: str) -> List[str]:
        """
        Generate ancient Chinese keywords from query.
        """
        try:
            from litellm import completion
        except ImportError:
            console.print("[red]❌ litellm not installed. Run: pip install litellm[/red]")
            return [query]

        prompt = f"""
你是一個精通《紅樓夢》與經史子集的古文專家。
用戶將輸入一個白話文問題，請提取其核心意圖，並**僅**輸出對應的 3-5 個古文關鍵詞、人物別稱或典故名。
不要輸出解釋，直接輸出關鍵詞，以空格分隔。

用戶輸入：{query}
關鍵詞：
"""
        
        try:
            console.print(f"[dim]Expanding query: '{query}'...[/dim]")
            response = completion(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                api_key=self.api_key,
                temperature=0.3,
                max_tokens=50
            )
            
            content = response.choices[0].message.content.strip()
            keywords = content.split()
            
            # Clean keywords
            keywords = [k.strip() for k in keywords if k.strip()]
            
            console.print(f"  ✨ Keywords: [cyan]{', '.join(keywords)}[/cyan]")
            return keywords
            
        except Exception as e:
            logger.error(f"Query expansion failed: {e}")
            console.print(f"[red]❌ Query expansion error: {e}[/red]")
            # Fallback to original query tokens if possible, or just return query as single keyword
            return [query]

def main():
    """Test Query Expander."""
    console.print(Panel.fit("[bold blue]Query Expander Test[/bold blue]"))
    
    # Check key
    if not os.getenv("OPENROUTER_API_KEY"):
         console.print("[red]Please set OPENROUTER_API_KEY environment variable to test.[/red]")
         return

    expander = QueryExpander(model_name="openrouter/deepseek/deepseek-chat") # Update specific model ID if needed
    
    queries = [
        "賈寶玉最後跟誰結婚？",
        "林黛玉是怎麼死的？",
        "紅樓夢裡誰管家？"
    ]
    
    for q in queries:
        console.print(f"\n[bold]Original:[/bold] {q}")
        expander.expand(q)

if __name__ == "__main__":
    main()
