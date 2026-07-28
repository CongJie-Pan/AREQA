"""Base OpenAI-compatible tool-calling agent loop."""

import os
from openai import OpenAI
from .memory import Memory
from .tools import ToolRegistry

DEFAULT_MODEL = "qwen/qwen3-235b-a22b-2507"

class Agent:
    """Run one model-owned tool-calling loop.

    Args:
        memory: Conversation memory owned by this agent instance.
        tool_registry: Tool registry visible to this agent.
        model: OpenRouter/OpenAI-compatible model route.
        max_iterations: Maximum model/tool loop iterations for one user turn.
        client: Optional OpenAI-compatible client, primarily for tests or
            parent/child agent sharing.
        name: Human-readable agent name used in trace events.
        role: Logical role such as ``main``, ``orchestrator``, or ``leaf``.
        depth: Delegation depth. Top-level agents use ``0``.
        trace_callback: Optional callable receiving safe event dictionaries.

    Side Effects:
        Appends user, assistant, and tool messages to ``memory``. Tool results
        are stored as JSON strings returned by ``ToolRegistry``.
    """

    def __init__(
        self,
        memory: Memory,
        tool_registry: ToolRegistry,
        model: str = DEFAULT_MODEL,
        max_iterations: int = 5,
        *,
        client=None,
        name: str = "agent",
        role: str = "main",
        depth: int = 0,
        trace_callback=None,
    ):
        self.client = client or OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY")
        )
        self.memory = memory
        self.tool_registry = tool_registry
        self.model = model
        self.max_iterations = max_iterations
        self.name = name
        self.role = role
        self.depth = depth
        self.trace_callback = trace_callback

    def run_conversation(self, user_message: str) -> str:
        """Process a user message and run the core agent loop.

        Args:
            user_message: Latest user or parent-agent instruction.

        Returns:
            The final assistant text, or a bounded error string when the model
            never produces a final answer.
        """
        self.memory.add_message("user", user_message)
        self._trace("agent_turn_started")
        
        iterations = 0
        while iterations < self.max_iterations:
            messages = self.memory.get_messages()
            tools = self.tool_registry.get_schemas()
            
            # API Call
            kwargs = {"model": self.model, "messages": messages}
            if tools:
                kwargs["tools"] = tools
                
            response = self.client.chat.completions.create(**kwargs)
            response_message = response.choices[0].message
            
            # If the model didn't want to call a tool, we're done
            if not response_message.tool_calls:
                self.memory.add_message("assistant", response_message.content)
                self._trace("agent_turn_completed", iterations=iterations + 1)
                return response_message.content

            # Add the assistant's tool_call request to memory
            self.memory.add_message("assistant", response_message.content, tool_calls=[
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments}
                }
                for tc in response_message.tool_calls
            ])

            # Execute tools
            for tool_call in response_message.tool_calls:
                tool_name = tool_call.function.name
                tool_args = tool_call.function.arguments
                print(f"  [Tool Call] {tool_name}({tool_args})")
                self._trace("agent_tool_call_started", tool_name=tool_name)
                
                result = self.tool_registry.execute_tool(tool_name, tool_args)
                print(f"  [Tool Result] {result}")
                self._trace("agent_tool_call_completed", tool_name=tool_name)
                
                self.memory.add_message("tool", result, tool_call_id=tool_call.id)
                
            iterations += 1

        self._trace("agent_turn_exhausted", iterations=iterations)
        return "Error: Max iterations reached without a final answer."

    def _trace(self, event: str, **metadata):
        """Emit a safe trace event when a trace callback is configured.

        Args:
            event: Stable event name.
            **metadata: Safe metadata. Raw prompts, model outputs, credentials,
                and tool results should not be added here.
        """
        if self.trace_callback is None:
            return
        payload = {
            "event": event,
            "agent": self.name,
            "role": self.role,
            "depth": self.depth,
        }
        payload.update(metadata)
        self.trace_callback(payload)
