import sys
from pathlib import Path
import asyncio
import os

# Add misc/gum to sys.path
project_root = Path(__file__).resolve().parents[1]
gum_dir = project_root / "misc" / "gum"
if str(gum_dir) not in sys.path:
    sys.path.insert(0, str(gum_dir))

from gum.gum import gum
from gum.observers import Observer
from gum.schemas import Update

class TextObserver(Observer):
    def __init__(self, name="TextChatObserver"):
        super().__init__(name)
        
    async def push_text(self, text: str):
        # We wrap the text in an Update object
        await self.update_queue.put(Update(content=text, content_type="input_text"))

    async def start(self):
        pass

    async def stop(self):
        pass
        
    async def _worker(self):
        while True:
            await asyncio.sleep(3600)

# Global instances
text_observer = None
gum_instance = None

async def init_gum_instance():
    global gum_instance, text_observer
    text_observer = TextObserver()
    
    # Initialize GUM
    data_dir = str(project_root / "data" / "gum_data")
    os.makedirs(data_dir, exist_ok=True)
    
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    
    gum_instance = gum(
        "default_user",
        "qwen/qwen3-235b-a22b-2507",
        text_observer,
        data_directory=data_dir,
        db_name="gum.db",
        api_key=api_key,
        min_batch_size=1, # Setting to 1 to see immediate results for QA
        max_batch_size=10,
    )
    await gum_instance.connect_db()
    gum_instance.start_update_loop()
    if gum_instance.batcher:
        await gum_instance.batcher.start()
    
    print("GUM instance initialized successfully.")
    return gum_instance

async def stop_gum_instance():
    global gum_instance
    if gum_instance:
        await gum_instance.stop_update_loop()
        if gum_instance.batcher:
            await gum_instance.batcher.stop()

async def push_observation(text: str):
    if text_observer:
        await text_observer.push_text(text)

async def get_all_memory():
    if not gum_instance:
        return []
    try:
        props = await gum_instance.recent(limit=100)
        return [
            {
                "id": p.id, 
                "text": p.text, 
                "confidence": p.confidence, 
                "updated_at": p.updated_at.isoformat() if p.updated_at else None
            } 
            for p in props
        ]
    except Exception as e:
        print(f"Error fetching memory: {e}")
        return []

async def get_suggestions():
    if not gum_instance:
        return []
    try:
        props = await gum_instance.recent(limit=10)
        if not props:
            return []
        
        from gum.schemas import get_schema
        from pydantic import BaseModel
        
        class SuggestionsResponse(BaseModel):
            suggestions: list[str]
            
        context = "\n".join([f"- {p.text} (confidence: {p.confidence})" for p in props])
        prompt = f"Based on the following facts about the user:\n{context}\n\nGenerate 3 short, engaging, and actionable suggestions for what the user might want to explore next in a classical Chinese literature (like Dream of the Red Chamber) QA system. Make them sound like natural questions the user could click to ask. Output exactly 3 strings in the array."
        
        rsp = await gum_instance.client.chat.completions.create(
            model=gum_instance.model,
            messages=[{"role": "user", "content": prompt}],
            response_format=get_schema(SuggestionsResponse.model_json_schema()),
        )
        import json
        data = json.loads(rsp.choices[0].message.content)
        return data.get("suggestions", [])
    except Exception as e:
        print(f"Error generating suggestions: {e}")
        return []

