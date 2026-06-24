BASE_SYSTEM_PROMPT = """You are AREQA, a helpful AI assistant specializing in the classic Chinese novel "Dream of the Red Chamber" (紅樓夢).
Your goal is to assist the user in learning, exploring the novel, and tracking their proficiency, while maintaining a persistent understanding of their preferences and facts about them.
If the user asks you to remember something, you MUST use the provided memory tools to store it.
Always check the USER PROFILE and MEMORY to personalize your responses.
"""

def build_system_prompt(base_prompt: str, user_snapshot: str, memory_snapshot: str) -> str:
    """
    組裝 System Prompt。
    這保證了 Cache 友善的層次結構：
    Layer 1: 穩定的基礎人格設定 (Base System Prompt)
    Layer 2: 相對穩定的 USER.md 快照
    Layer 3: 變動較頻繁的 MEMORY.md 快照
    """
    parts = [base_prompt]
    
    if user_snapshot:
        parts.append(user_snapshot)
        
    if memory_snapshot:
        parts.append(memory_snapshot)
        
    return "\n\n".join(parts)
