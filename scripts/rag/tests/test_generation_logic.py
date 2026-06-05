
import sys
from pathlib import Path
from rich.console import Console

# Add scripts/rag to path
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.append(str(PROJECT_ROOT / "scripts" / "rag"))

from p3_t03_enhanced_retrieval import generate_answer

console = Console()

def test_generation():
    console.print("[bold blue]Testing Generation Logic (Mocked Retrieval)[/bold blue]")
    
    query = "林黛玉的性格特點是什麼？"
    
    # Mock retrieved chunks (mimicking REAL data on disk)
    mock_chunks = [
        {
            "chunk_id": "poem_rc_poem_021_01",
            "text": "花謝花飛花滿天，紅消香斷有誰憐？... (葬花吟片段)",
            "source": "詩詞", 
            "metadata": {"original_id": "rc_poem_021", "title": "葬花吟", "chapter_id": 27}
        },
        {
            "chunk_id": "wiki_史湘雲_001",
            "text": "史湘雲是《紅樓夢》中的主要人物，首次出場於第二十回...",
            "source": "維基",
            "metadata": {"title": "史湘雲", "section": "簡介", "url": "..."}
        }
    ]
    
    answer = generate_answer(query, mock_chunks)
    
    console.print("\n[bold green]Final Answer:[/bold green]")
    console.print(answer)

if __name__ == "__main__":
    test_generation()
