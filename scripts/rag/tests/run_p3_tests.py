
import unittest
import sys
from pathlib import Path
from rich.console import Console
from rich.panel import Panel

console = Console()

def run_tests():
    console.print(Panel.fit("[bold blue]Running RAG V3 Unit & Integration Tests[/bold blue]"))
    
    loader = unittest.TestLoader()
    # Path(__file__) is scripts/rag/run_p3_tests.py
    # Project root is ../../
    project_root = Path(__file__).parent.parent.parent.parent
    start_dir = project_root / "tests" / "rag"
    
    # ensure project root is in sys.path so tests can import from scripts
    sys.path.append(str(project_root))
    
    suite = loader.discover(str(start_dir), pattern="test_*.py")
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    if result.wasSuccessful():
        console.print("[bold green]✅ All Tests Passed![/bold green]")
        sys.exit(0)
    else:
        console.print("[bold red]❌ Some Tests Failed![/bold red]")
        sys.exit(1)

if __name__ == "__main__":
    run_tests()
