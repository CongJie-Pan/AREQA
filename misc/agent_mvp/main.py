"""CLI entry point for the orchestration-oriented Agent MVP."""

import ctypes
import os
import sys

from dotenv import load_dotenv

from core.orchestrator import OrchestratorAgent
from core.tools import ToolRegistry


UTF8_CODE_PAGE = 65001


def configure_console_encoding() -> None:
    """Configure the interactive CLI to handle UTF-8 text.

    Side Effects:
        On Windows, attempts to set the console input and output code pages to
        UTF-8. For all platforms, asks Python's standard streams to encode and
        decode as UTF-8 when the stream object supports ``reconfigure``.

    Compatibility:
        Encoding setup must be best-effort because CI, redirected output, and
        IDE terminals may expose stream wrappers without ``reconfigure`` or a
        native Windows console handle. Failures are intentionally ignored so the
        CLI can still start in constrained environments.
    """
    if os.name == "nt":
        try:
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleCP(UTF8_CODE_PAGE)
            kernel32.SetConsoleOutputCP(UTF8_CODE_PAGE)
        except (AttributeError, OSError):
            pass

    for stream_name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None or not hasattr(stream, "reconfigure"):
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass


def calculator(a: float, b: float, operator: str) -> float:
    """Perform basic arithmetic operations.

    Args:
        a: Left operand.
        b: Right operand.
        operator: One of ``+``, ``-``, ``*``, ``/`` or a plain-English alias.

    Returns:
        The arithmetic result.

    Raises:
        ValueError: If ``operator`` is unsupported.
    """
    op = operator.lower().strip()
    if op in ["+", "add", "plus"]:
        return a + b
    if op in ["-", "subtract", "minus"]:
        return a - b
    if op in ["*", "x", "multiply", "times"]:
        return a * b
    if op in ["/", "divide", "div"]:
        return a / b
    raise ValueError(f"Unknown operator: {operator}")


def get_weather(location: str) -> str:
    """Get mock weather for a location.

    Args:
        location: Location name supplied by the model.

    Returns:
        A deterministic mock weather report for demonstration.
    """
    return f"The weather in {location} is sunny and 75F."


def build_base_tools() -> ToolRegistry:
    """Create the normal tool surface shared by orchestrator and children.

    Returns:
        A fresh registry with non-delegation tools. ``OrchestratorAgent`` adds
        ``delegate_task`` separately so leaf workers cannot recurse by default.
    """
    registry = ToolRegistry()
    registry.register_tool(calculator, "Calculate basic math operations.")
    registry.register_tool(get_weather, "Get weather for a location.")
    return registry


def print_trace(event: dict) -> None:
    """Print compact orchestration trace events for local debugging.

    Args:
        event: Safe trace event emitted by the agent runtime.
    """
    name = event.get("event", "event")
    role = event.get("role")
    depth = event.get("depth")
    delegation_id = event.get("delegation_id")
    parts = [f"[trace] {name}"]
    if role:
        parts.append(f"role={role}")
    if depth is not None:
        parts.append(f"depth={depth}")
    if delegation_id:
        parts.append(f"id={delegation_id}")
    print(" ".join(parts))


def main() -> None:
    """Run the interactive orchestration-agent CLI."""
    configure_console_encoding()
    load_dotenv()
    if not os.getenv("OPENROUTER_API_KEY"):
        print("Warning: OPENROUTER_API_KEY not found in environment or .env file.")

    agent = OrchestratorAgent(
        base_tool_factory=build_base_tools,
        max_iterations=8,
        child_max_iterations=5,
        max_spawn_depth=2,
        trace_callback=print_trace,
    )

    print("=== Orchestration Agent MVP ===")
    print("Type 'exit' or 'quit' to stop.\n")

    while True:
        try:
            user_input = input("User: ")
            if user_input.strip().lower() in ["exit", "quit"]:
                break
            if not user_input.strip():
                continue

            response = agent.run_conversation(user_input)
            print(f"Assistant: {response}\n")
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"\nError: {e}\n")


if __name__ == "__main__":
    main()
