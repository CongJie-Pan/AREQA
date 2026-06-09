import asyncio
import os
import random
import logging
from typing import Optional, List, Tuple
from sqlalchemy import delete, update

# Import GUM package from parent directories
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
from gum import gum
from gum.observers.observer import Observer
from gum.schemas import Update
from gum.models import Proposition, Observation

# Global GUM instance and background task references
gum_instance: Optional[gum] = None
recording_task: Optional[asyncio.Task] = None

async def init_gum(user_name: str, model_name: str, api_key: str) -> gum:
    """
    Initialize the GUM instance.
    """
    global gum_instance
    
    # Store settings in environment variables if needed
    os.environ["OPENAI_API_KEY"] = api_key
    
    kwargs = {}
    if "GUM_TEST_DATA_DIR" in os.environ:
        kwargs["data_directory"] = os.environ["GUM_TEST_DATA_DIR"]
        kwargs["db_name"] = os.path.join(os.environ["GUM_TEST_DATA_DIR"], "gum.db")
        
    gum_instance = gum(
        user_name,
        model_name,
        # No built-in mock observers anymore, we rely on push_observation
        api_key=api_key,
        audit_enabled=True,
        min_batch_size=1,  # Set low batch size for quick processing of screenshots
        max_batch_size=3,
        **kwargs
    )
    
    await gum_instance.connect_db()
    return gum_instance

async def push_observation(content: str, content_type: str = "input_image"):
    """
    Push a real observation (like a screenshot) into the GUM batcher.
    """
    global gum_instance
    if not gum_instance:
        return False
        
    logging.info(f"Received real observation via push_observation! content_type: {content_type}, length: {len(content)}")
        
        
    gum_instance.batcher.push(
        observer_name="ScreenCapture",
        content=content,
        content_type=content_type
    )
    return True

async def run_gum_loop(user_name: str, model_name: str, api_key: str):
    """
    Background loop runner for GUM instance.
    """
    global gum_instance
    await init_gum(user_name, model_name, api_key)
    
    # Run GUM inside context manager
    async with gum_instance:
        # Keep running
        while True:
            await asyncio.sleep(1)

def start_recording(user_name: str, model_name: str, api_key: str):
    """
    Start the GUM update loop in a background asyncio task.
    """
    global recording_task
    if recording_task and not recording_task.done():
        return
    
    recording_task = asyncio.create_task(run_gum_loop(user_name, model_name, api_key))

async def stop_recording():
    """
    Stop the GUM background task.
    """
    global recording_task, gum_instance
    if recording_task:
        recording_task.cancel()
        try:
            await recording_task
        except asyncio.CancelledError:
            pass
        recording_task = None
    
    gum_instance = None

async def get_all_propositions() -> List[dict]:
    """
    Get all propositions from GUM database.
    """
    global gum_instance
    if not gum_instance:
        return []
    
    # Retrieve recent propositions
    props = await gum_instance.recent(limit=50)
    
    result = []
    for p in props:
        result.append({
            "id": p.id,
            "text": p.text,
            "reasoning": p.reasoning,
            "confidence": p.confidence,
            "created_at": p.created_at.isoformat() if hasattr(p.created_at, "isoformat") else str(p.created_at)
        })
    return result

async def update_prop(prop_id: int, text: str, confidence: int) -> bool:
    """
    Update an existing proposition in GUM database.
    """
    global gum_instance
    if not gum_instance:
        return False
        
    async with gum_instance._session() as session:
        await session.execute(
            update(Proposition)
            .where(Proposition.id == prop_id)
            .values(text=text, confidence=confidence)
        )
    return True

async def delete_prop(prop_id: int) -> bool:
    """
    Delete a proposition from GUM database.
    """
    global gum_instance
    if not gum_instance:
        return False
        
    async with gum_instance._session() as session:
        await session.execute(
            delete(Proposition)
            .where(Proposition.id == prop_id)
        )
    return True

async def delete_all_props() -> bool:
    """
    Delete all propositions from GUM database.
    """
    global gum_instance
    if not gum_instance:
        return False
        
    async with gum_instance._session() as session:
        await session.execute(delete(Proposition))
    return True

async def generate_suggestions() -> List[dict]:
    """
    Generate proactive suggestions based on current propositions using LLM.
    """
    global gum_instance
    if not gum_instance:
        return []
        
    props = await gum_instance.recent(limit=15)
    if not props:
        # Return fallback suggestions if no propositions exist yet
        return [
            {
                "id": "s1",
                "title": "開始記錄您的電腦活動",
                "description": "Gumbo 需要觀察您的日常工作來建立命題與建議。請啟用錄製以開始。",
                "benefit": 9,
                "confidence": 10
            }
        ]
        
    props_text = "\n".join([f"- Proposition: {p.text} (Confidence: {p.confidence}/10)" for p in props])
    prompt = f"""
You are the AI assistant Gumbo. Based on the user's current behavioral propositions below, generate a JSON object containing a list of 3-5 concrete, personalized, and actionable suggestions.
If the propositions indicate the user is struggling, suggest a solution. If they show a pattern of interest, suggest related content or action.
Ensure that ALL text fields in your response are written in Traditional Chinese / 繁體中文.

User Propositions:
{props_text}

Format the response exactly as a JSON object:
{{
  "suggestions": [
    {{
      "id": "unique_id_string",
      "title": "Short actionable suggestion title",
      "description": "Clear description explaining what Gumbo noticed and what Gumbo can do to help (e.g. create a outline, search for solutions, schedule a reminder)",
      "benefit": 8, // Benefit score from 1 to 10
      "confidence": 9 // Confidence score from 1 to 10
    }}
  ]
}}
"""
    try:
        response = await gum_instance.client.chat.completions.create(
            model=gum_instance.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        import json
        data = json.loads(response.choices[0].message.content)
        return data.get("suggestions", [])
    except Exception as e:
        logging.error(f"Error generating suggestions: {e}")
        # Return fallback mock suggestions based on props
        return [
            {
                "id": "s_fallback_1",
                "title": f"Help with: {props[0].text[:30]}...",
                "description": f"Based on the proposition: '{props[0].text}', Gumbo can assist you in finding documentation, drafting outlines, or preparing templates.",
                "benefit": 7,
                "confidence": 8
            }
        ]
