# schemas.py

from __future__ import annotations
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, ConfigDict

class AuditSchema(BaseModel):
    """
    Output produced by the privacy-audit LLM call.
    """
    is_new_information: bool = Field(..., description="Whether the message reveals anything not seen before")
    data_type:          str  = Field(..., description="Category of data being disclosed")
    subject:            str  = Field(..., description="Who the data is about")
    recipient:          str  = Field(..., description="Who receives the data")
    transmit_data:      bool = Field(..., description="Should downstream processing continue")

    model_config = ConfigDict(extra="forbid")

class PropositionItem(BaseModel):
    reasoning: str = Field(..., description="The reasoning for the proposition")
    proposition: str = Field(..., description="The proposition string")
    
    # Contextual Intent Filters (STITCH)
    context_scope: Optional[str] = Field(None, description="The overarching topic or subject area (e.g., 'Python Programming', 'History')")
    event_types: Optional[List[str]] = Field(default_factory=list, description="The action or nature of the observation (e.g., 'Questioning', 'Clarification', 'Learning')")
    target: Optional[str] = Field(None, description="The main entity involved (e.g., 'for loop', 'Napoleon')")
    functional_type_seeds: Optional[List[str]] = Field(default_factory=list, description="Functional or pragmatic types covering details driving the utterance")
    
    confidence: Optional[int] = Field(
        ...,
        description="Confidence score from 1 (low) to 10 (high)"
    )
    decay: Optional[int] = Field(
        ...,
        description="Decay score from 1 (low) to 10 (high)"
    )

    model_config = ConfigDict(extra="forbid")

class IntentPredictionSchema(BaseModel):
    """Schema for predicting user intent to filter memory context."""
    selected_context_scopes: List[str] = Field(..., description="Selected context scopes for the query")
    selected_event_types: List[str] = Field(..., description="Selected event types for the query")
    selected_targets: List[str] = Field(..., description="Selected targets for the query")
    selected_functional_type_seeds: List[str] = Field(..., description="Selected functional types for the query")
    
    model_config = ConfigDict(extra="forbid")

class PropositionSchema(BaseModel):
    propositions: List[PropositionItem] = Field(
        ...,
        description="Up to K propositions"
    )
    model_config = ConfigDict(extra="forbid")

class Update(BaseModel):
    content: str = Field(..., description="The content of the update")
    content_type: Literal["input_text", "input_image"] = Field(..., description="The type of the update")

RelationLabel = Literal["IDENTICAL", "SIMILAR", "UNRELATED"]

class RelationItem(BaseModel):
    source: int                     = Field(description="Proposition ID")
    label:  RelationLabel           = Field(description="Relationship label")

    # give target a default_factory so the JSON‐schema default is [] (allowed)
    target: List[int] = Field(
        default_factory=list,
        description="IDs of other propositions (empty if none)"
    )

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "required": ["source", "label", "target"]
        }
    )


class RelationSchema(BaseModel):
    relations: List[RelationItem]

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "required": ["relations"]
        }
    )

def get_schema(json_schema):
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "json_output",
            "schema": json_schema,
        },
    }

UPDATE_MAP = {
    "input_text": "text",
    "input_image": "image_url",
}
