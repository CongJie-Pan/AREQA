"""Tool registration and execution helpers for OpenAI-style tool calling."""

import inspect
import json
from typing import Callable, Dict, Any

class ToolRegistry:
    """Register Python callables as model-callable tools.

    The registry owns two views of the same tool surface: executable Python
    callables by name and JSON schemas suitable for OpenAI-compatible chat
    completions. It keeps execution failures inside tool results so the agent
    loop can hand recoverable errors back to the model without crashing the
    current turn.
    """

    def __init__(self):
        self.tools: Dict[str, Callable] = {}
        self.schemas: list = []

    def register_tool(self, func: Callable, description: str = None, name: str = None):
        """Register a Python function as a tool.

        Args:
            func: Callable executed when the model requests this tool.
            description: Optional tool description exposed in the model schema.
            name: Optional public tool name. This is useful for closures whose
                Python ``__name__`` would otherwise be generic.
        """
        name = name or func.__name__
        self.tools[name] = func
        
        # Build schema
        sig = inspect.signature(func)
        schema = {
            "type": "function",
            "function": {
                "name": name,
                "description": description or func.__doc__ or f"Execute {name}",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        }
        
        for param_name, param in sig.parameters.items():
            param_type = "string"
            if param.annotation == int:
                param_type = "integer"
            elif param.annotation == float:
                param_type = "number"
            elif param.annotation == bool:
                param_type = "boolean"
                
            schema["function"]["parameters"]["properties"][param_name] = {
                "type": param_type
            }
            if param.default == inspect.Parameter.empty:
                schema["function"]["parameters"]["required"].append(param_name)
                
        self.schemas.append(schema)

    def execute_tool(self, name: str, kwargs_json: str | dict | None) -> str:
        """Execute a registered tool by name with JSON kwargs.

        Args:
            name: Registered tool name.
            kwargs_json: JSON object string emitted by the model, a dict from a
                test harness, or ``None`` for no arguments.

        Returns:
            A JSON string with either ``{"result": ...}`` or ``{"error": ...}``.
        """
        if name not in self.tools:
            return json.dumps({"error": f"Tool '{name}' not found."})
        
        try:
            if isinstance(kwargs_json, dict):
                kwargs = kwargs_json
            elif kwargs_json is None or not str(kwargs_json).strip():
                kwargs = {}
            else:
                kwargs = json.loads(kwargs_json)
            result = self.tools[name](**kwargs)
            return json.dumps({"result": result})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def get_schemas(self) -> list:
        return self.schemas
