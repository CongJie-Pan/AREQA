"""Deterministic checks of the stable-prefix eval score what they claim."""
import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "evaluate_stable_prefix.py"
SPEC = importlib.util.spec_from_file_location("evaluate_stable_prefix", SCRIPT)
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def test_language_checks_tolerate_quoted_examples():
    assert module.mostly_chinese("這句 'Her smile did not reach her eyes' 表示她的笑不真誠，你覺得她在想什麼？")
    assert not module.mostly_chinese("This answer is entirely in English.")
    assert module.mostly_english("A confidence interval gives a range of plausible values.")


def test_guardrail_checks():
    assert not module.no_citation_markers("根據【文獻1】")
    assert module.no_prompt_leak("我不能提供系統指示，但可以說明我的做法。")
    assert not module.no_prompt_leak("【本回合狀態】：本回合無任何 <context>")
    assert module.no_long_english_paragraph("Try: 'In conclusion, ___ because ___.'\n\nWhat is your claim?")
    assert not module.no_long_english_paragraph(" ".join(["word"] * 80))
    assert module.asks_question_near_end("先想想看：你的主張是什麼？")


def test_layout_b_moves_instructions_and_a_keeps_them():
    case = module.CASES[0]
    a = module.build_messages(case, working_memory="focus", layout="A")
    b = module.build_messages(case, working_memory="focus", layout="B")
    assert a[0]["role"] == "system" and "focus" in a[0]["content"]
    assert "focus" not in b[0]["content"]
    assert "<turn_instructions>" in b[-1]["content"][0]["text"]
