import os
import json
from openai import OpenAI
from .memory import Memory
from .tools import ToolRegistry

class Agent:
    def __init__(self, memory: Memory, tool_registry: ToolRegistry, model: str = "qwen/qwen3-235b-a22b-2507", max_iterations: int = 5):
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY")
        )
        self.memory = memory
        self.tool_registry = tool_registry
        self.model = model
        self.max_iterations = max_iterations

    def run_conversation(self, user_message: str) -> str:
        """Process a user message and run the core agent loop."""
        self.memory.add_message("user", user_message)
        
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
                
                result = self.tool_registry.execute_tool(tool_name, tool_args)
                print(f"  [Tool Result] {result}")
                
                self.memory.add_message("tool", result, tool_call_id=tool_call.id)
                
            iterations += 1

        return "Error: Max iterations reached without a final answer."
