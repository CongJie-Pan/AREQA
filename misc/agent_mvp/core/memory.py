from typing import List, Dict

class Memory:
    def __init__(self, system_prompt: str = None):
        self.messages: List[Dict[str, str]] = []
        if system_prompt:
            self.add_message("system", system_prompt)

    def add_message(self, role: str, content: str, **kwargs):
        """Add a message to the memory."""
        msg = {"role": role, "content": content}
        # If content is None, OpenAI expects it to be omitted or null, but dict updating handles it
        msg.update(kwargs)
        self.messages.append(msg)

    def get_messages(self) -> List[Dict[str, str]]:
        """Retrieve all messages."""
        return self.messages
