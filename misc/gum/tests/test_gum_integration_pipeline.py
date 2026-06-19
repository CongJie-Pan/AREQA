import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
import json
from gum.gum import gum

def test_gum_query_pipeline():
    async def run_test():
        with patch("gum.gum.search_propositions_bm25", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = []
            
            g = gum(user_name="test_user", model="fake-model")
            
            # Mock internal session and client
            mock_session_ctx = AsyncMock()
            mock_session = AsyncMock()
            mock_session_ctx.__aenter__.return_value = mock_session
            g._session = lambda: mock_session_ctx
            
            # Mock DB results for candidates
            mock_result = MagicMock()
            mock_row = type("Row", (object,), {
                "context_scope": "Test Scope",
                "event_types": json.dumps(["Test Event"]),
                "target": "Test Target",
                "functional_type_seeds": json.dumps(["Test Func"])
            })()
            mock_result.fetchall.return_value = [mock_row]
            mock_session.execute.return_value = mock_result
            
            # Mock LLM intent prediction response
            mock_response = AsyncMock()
            mock_response.choices = [
                type("Choice", (object,), {
                    "message": type("Message", (object,), {
                        "content": json.dumps({
                            "selected_context_scopes": ["Test Scope"],
                            "selected_event_types": ["Test Event"],
                            "selected_targets": ["Test Target"],
                            "selected_functional_type_seeds": ["Test Func"]
                        })
                    })()
                })()
            ]
            g.client = AsyncMock()
            g.client.chat.completions.create.return_value = mock_response
            
            # Run query
            await g.query("test query")
            
            # Check if STITCH intent prediction LLM was called
            assert g.client.chat.completions.create.call_count == 1
            
            # Verify search was called with correct intent labels
            mock_search.assert_called_once()
            args, kwargs = mock_search.call_args
            assert "selected_labels" in kwargs
            labels = kwargs["selected_labels"]
            assert labels["selected_context_scopes"] == ["Test Scope"]
            assert labels["selected_targets"] == ["Test Target"]
            
    asyncio.run(run_test())
