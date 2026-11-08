"""Protect PDF role extraction without uploading private fixtures to providers."""
import sys
from types import SimpleNamespace

import pytest

from scripts.evaluate_conversation_compaction import extract_messages


def test_pdf_parser_preserves_roles_and_duplicate_submissions(monkeypatch, tmp_path):
    page = SimpleNamespace(extract_text=lambda: 'AREQA 對話紀錄\n👤 您\nquestion\n----------\n🤖 AREQA\nanswer\n👤 您\nquestion\n👤 您\nquestion')
    monkeypatch.setitem(sys.modules, 'pypdf', SimpleNamespace(PdfReader=lambda _: SimpleNamespace(pages=[page])))
    messages, pages = extract_messages(tmp_path / 'source.pdf')
    assert pages == 1
    assert [m['role'] for m in messages] == ['user', 'assistant', 'user', 'user']
    assert [m['content'] for m in messages] == ['question', 'answer', 'question', 'question']


def test_pdf_parser_refuses_unmarked_text(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, 'pypdf', SimpleNamespace(PdfReader=lambda _: SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda: 'no transcript roles')])))
    with pytest.raises(ValueError, match='role markers'):
        extract_messages(tmp_path / 'source.pdf')
