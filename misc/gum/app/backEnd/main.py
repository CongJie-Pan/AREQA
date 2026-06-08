import os
from fastapi import FastAPI, HTTPException, BackgroundTasks, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import logging

from core import gum_manager

app = FastAPI(title="Gumbo AI Assistant Backend")

# Configure CORS so the React app can communicate with the backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow all origins for dev simplicity
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Pydantic Schemas ---
class SettingsPayload(BaseModel):
    user_name: str = "default_user"
    llm_api_key: str
    enable_screen_capture: bool = False
    model_name: str = "gpt-4o-mini"

class PropositionUpdate(BaseModel):
    text: str
    confidence: int

class FeedbackPayload(BaseModel):
    suggestion_id: str
    is_positive: bool
    text_feedback: Optional[str] = None

# Global configs cache (in-memory for simple settings management)
settings_store = {
    "user_name": "default_user",
    "llm_api_key": os.getenv("OPENAI_API_KEY", ""),
    "enable_screen_capture": False,
    "model_name": "gpt-4o-mini"
}

@app.post("/api/settings")
async def update_settings(payload: SettingsPayload):
    """
    Save settings and initialize or re-initialize GUM.
    """
    settings_store["user_name"] = payload.user_name
    settings_store["llm_api_key"] = payload.llm_api_key
    settings_store["enable_screen_capture"] = payload.enable_screen_capture
    settings_store["model_name"] = payload.model_name
    
    # Initialize GUM instance with the provided settings
    try:
        await gum_manager.init_gum(
            user_name=payload.user_name,
            model_name=payload.model_name,
            api_key=payload.llm_api_key
        )
        return {"status": "success", "message": "Settings updated and GUM initialized successfully."}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize GUM: {str(e)}"
        )

@app.post("/api/recording/start")
async def start_recording():
    """
    Start behavioral recording loop.
    """
    api_key = settings_store["llm_api_key"]
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="API Key is not configured. Please save your API Key in Settings first."
        )
    
    gum_manager.start_recording(
        user_name=settings_store["user_name"],
        model_name=settings_store["model_name"],
        api_key=api_key
    )
    return {"status": "success", "message": "Recording started in background."}

@app.post("/api/recording/stop")
async def stop_recording():
    """
    Stop behavioral recording loop.
    """
    await gum_manager.stop_recording()
    return {"status": "success", "message": "Recording stopped."}

@app.get("/api/recording/status")
async def get_recording_status():
    """
    Check if GUM recording loop is running.
    """
    is_active = (gum_manager.recording_task is not None and 
                 not gum_manager.recording_task.done())
    return {
        "is_recording": is_active,
        "user_name": settings_store["user_name"],
        "model_name": settings_store["model_name"]
    }

@app.get("/api/memory")
async def get_memory():
    """
    Retrieve all propositions.
    """
    if not gum_manager.gum_instance:
        # Auto-initialize if settings have an API key
        if settings_store["llm_api_key"]:
            await gum_manager.init_gum(
                user_name=settings_store["user_name"],
                model_name=settings_store["model_name"],
                api_key=settings_store["llm_api_key"]
            )
        else:
            return {"propositions": [], "warning": "GUM not initialized. Please set LLM API Key."}
            
    try:
        props = await gum_manager.get_all_propositions()
        return {"propositions": props}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch propositions: {str(e)}"
        )

@app.put("/api/memory/{prop_id}")
async def update_memory(prop_id: int, payload: PropositionUpdate):
    """
    Manually update a proposition text or confidence.
    """
    success = await gum_manager.update_prop(prop_id, payload.text, payload.confidence)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to update proposition. Is GUM initialized?"
        )
    return {"status": "success", "message": "Proposition updated successfully."}

@app.delete("/api/memory/{prop_id}")
async def delete_memory(prop_id: int):
    """
    Delete a proposition.
    """
    success = await gum_manager.delete_prop(prop_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to delete proposition. Is GUM initialized?"
        )
    return {"status": "success", "message": "Proposition deleted successfully."}

@app.get("/api/suggestions")
async def get_suggestions():
    """
    Generate actionable suggestions based on propositions.
    """
    if not gum_manager.gum_instance:
        if settings_store["llm_api_key"]:
            await gum_manager.init_gum(
                user_name=settings_store["user_name"],
                model_name=settings_store["model_name"],
                api_key=settings_store["llm_api_key"]
            )
        else:
            return {"suggestions": []}
            
    try:
        suggestions = await gum_manager.generate_suggestions()
        return {"suggestions": suggestions}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate suggestions: {str(e)}"
        )

@app.post("/api/feedback")
async def submit_feedback(payload: FeedbackPayload):
    """
    Handle user feedback on a suggestion and pass it back to GUM.
    """
    if not gum_manager.gum_instance:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GUM not initialized."
        )
        
    feedback_str = (f"User {'liked' if payload.is_positive else 'disliked'} "
                    f"suggestion ID {payload.suggestion_id}.")
    if payload.text_feedback:
        feedback_str += f" Text feedback: {payload.text_feedback}"
        
    try:
        # Feed the feedback back as an observation
        from gum.schemas import Update
        update_obj = Update(content=feedback_str, content_type="input_text")
        await gum_manager.gum_instance.batcher.add_observation(
            observer_name="UserFeedback",
            content=update_obj.content,
            content_type=update_obj.content_type
        )
        return {"status": "success", "message": "Feedback submitted to GUM."}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit feedback: {str(e)}"
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
