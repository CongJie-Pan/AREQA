import os
from dotenv import load_dotenv
from core.memory import Memory
from core.tools import ToolRegistry
from core.agent import Agent

# Define some default tools
def calculator(a: float, b: float, operator: str) -> float:
    """Perform basic arithmetic operations. operator must be one of: '+', '-', '*', '/'"""
    op = operator.lower().strip()
    if op in ['+', 'add', 'plus']: return a + b
    elif op in ['-', 'subtract', 'minus']: return a - b
    elif op in ['*', 'x', 'multiply', 'times']: return a * b
    elif op in ['/', 'divide']: return a / b
    else: raise ValueError(f"Unknown operator: {operator}")

def get_weather(location: str) -> str:
    """Get the weather for a given location."""
    # Mock implementation
    return f"The weather in {location} is sunny and 75°F."

def main():
    # Load env variables (API keys)
    load_dotenv()
    if not os.getenv("OPENROUTER_API_KEY"):
        print("Warning: OPENROUTER_API_KEY not found in environment or .env file.")

    # Initialize components
    memory = Memory(system_prompt="You are a helpful AI assistant. Use tools when necessary.")
    
    registry = ToolRegistry()
    registry.register_tool(calculator, "Calculate basic math operations.")
    registry.register_tool(get_weather, "Get weather for a location.")
    
    agent = Agent(memory=memory, tool_registry=registry)

    print("=== Agent MVP ===")
    print("Type 'exit' or 'quit' to stop.\n")
    
    while True:
        try:
            user_input = input("User: ")
            if user_input.strip().lower() in ['exit', 'quit']:
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
