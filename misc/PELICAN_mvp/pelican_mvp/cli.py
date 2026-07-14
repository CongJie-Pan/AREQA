"""Interactive, observable command-line interface for the PELICAN MVP."""

from __future__ import annotations

import argparse
from pathlib import Path

from .engine import PelicanEngine
from .models import TurnOutcome
from .state_store import StateStoreError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PELICAN knowledge-state tutoring MVP")
    parser.add_argument("--learner-id", default="demo_student", help="Persistent learner identifier")
    parser.add_argument("--mode", choices=("rule", "llm"), default="rule", help="Tutoring mode")
    return parser


def render(outcome: TurnOutcome) -> None:
    print(f"\n教師：{outcome.message}")
    if outcome.node_id:
        print(f"[目前節點] {outcome.node_id}")
    if outcome.category:
        print(f"[學生回應分類] {outcome.category.value}")
    if outcome.strategy:
        print(f"[教學策略] {outcome.strategy.value}")
    if outcome.state_changes:
        print("[狀態更新] " + "；".join(outcome.state_changes))
    print(f"[下一步依據] {outcome.next_reason}")


def main() -> int:
    args = build_parser().parse_args()
    data_dir = Path(__file__).resolve().parents[1] / "data"
    try:
        engine = PelicanEngine(data_dir, args.learner_id, args.mode)
        print("=== PELICAN CLI MVP ===")
        print("指令：tree、state、history、mode rule、mode llm、reset、show answer、quit")
        render(engine.start())
        while True:
            try:
                user_input = input("\n學生：").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n已離開。")
                return 0
            if user_input.lower() in {"quit", "exit"}:
                print("已保存學習狀態。")
                return 0
            if user_input == "tree":
                print(engine.tree_summary())
                continue
            if user_input == "state":
                print(engine.state.to_dict())
                continue
            if user_input == "history":
                print(engine.history_summary())
                continue
            if user_input.startswith("mode "):
                render(engine.switch_mode(user_input.removeprefix("mode ").strip()))
                continue
            if user_input == "reset":
                render(engine.reset())
                continue
            render(engine.respond(user_input))
    except (ValueError, StateStoreError, RuntimeError) as exc:
        print(f"錯誤：{exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

