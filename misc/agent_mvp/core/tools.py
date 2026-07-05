import inspect
import json
from typing import Callable, Dict, Any

class ToolRegistry:
    def __init__(self):
        self.tools: Dict[str, Callable] = {}
        self.schemas: list = []

    def register_tool(self, func: Callable, description: str = None):
        """Register a Python function as a tool."""
        name = func.__name__
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

    def execute_tool(self, name: str, kwargs_json: str) -> str:
        """Execute a registered tool by name with JSON kwargs."""
        if name not in self.tools:
            return json.dumps({"error": f"Tool '{name}' not found."})
        
        try:
            kwargs = json.loads(kwargs_json)
            result = self.tools[name](**kwargs)
            return json.dumps({"result": result})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def get_schemas(self) -> list:
        return self.schemas
