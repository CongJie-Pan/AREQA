import pytest
from pathlib import Path

def test_project_root_is_module_constant():
    """驗證 PROJECT_ROOT 已為模組常數且路徑正確。"""
    from backend.main import PROJECT_ROOT
    assert isinstance(PROJECT_ROOT, Path)
    assert PROJECT_ROOT.name == "AREQA"
    assert (PROJECT_ROOT / "backend" / "main.py").exists()
