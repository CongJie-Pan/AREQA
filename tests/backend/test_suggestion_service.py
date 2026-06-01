import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from src.main.python.services.suggestion_service import SuggestionService

@pytest.mark.asyncio
async def test_suggestion_service_success():
    # Mock the AsyncOpenAI client
    with patch('src.main.python.services.suggestion_service.AsyncOpenAI') as mock_openai:
        mock_client = mock_openai.return_value
        mock_client.chat.completions.create = AsyncMock()
        
        # Mock successful JSON response
        suggestions_json = '{"suggestions": ["賈寶玉的性格特點？", "林黛玉的詩作有哪些？", "大觀園的建築風格？"]}'
        mock_response = AsyncMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content=suggestions_json))
        ]
        mock_client.chat.completions.create.return_value = mock_response
        
        service = SuggestionService(api_key="test_key")
        
        # Mock reranked results (list of objects with text and source)
        mock_results = [
            MagicMock(text="寶玉愛女孩", source="紅樓夢第一回"),
            MagicMock(text="黛玉葬花", source="紅樓夢第二十七回")
        ]
        
        suggestions = await service.generate_suggestions(
            user_query="紅樓夢有哪些人物？",
            answer_text="有很多人物，如寶玉、黛玉等。",
            reranked_results=mock_results
        )
        
        assert len(suggestions) == 3
        assert "賈寶玉的性格特點？" in suggestions
        assert mock_client.chat.completions.create.called

@pytest.mark.asyncio
async def test_suggestion_service_malformed_json():
    # Test that the service fails gracefully with malformed JSON
    with patch('src.main.python.services.suggestion_service.AsyncOpenAI') as mock_openai:
        mock_client = mock_openai.return_value
        mock_client.chat.completions.create = AsyncMock()
        
        mock_response = AsyncMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="not a json"))
        ]
        mock_client.chat.completions.create.return_value = mock_response
        
        service = SuggestionService(api_key="test_key")
        suggestions = await service.generate_suggestions("query", "answer", [])

        assert suggestions == []

@pytest.mark.asyncio
async def test_suggestion_service_timeout():
    # Test that the service fails gracefully on API error
    with patch('src.main.python.services.suggestion_service.AsyncOpenAI') as mock_openai:
        mock_client = mock_openai.return_value
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("Timeout"))
        
        service = SuggestionService(api_key="test_key")
        suggestions = await service.generate_suggestions("query", "answer", [])
        
        assert suggestions == []

@pytest.mark.asyncio
async def test_suggestion_language_conversion():
    # Test that Simplified Chinese output is forcibly converted to Traditional Chinese
    with patch('src.main.python.services.suggestion_service.AsyncOpenAI') as mock_openai:
        mock_client = mock_openai.return_value
        mock_client.chat.completions.create = AsyncMock()

        # Simplified Chinese suggestions
        sc_json = '{"suggestions": ["贾宝玉为什么讨厌四书五经？", "林黛玉的性格特点是什么？", "大观园是怎么建成的？"]}'
        mock_response = AsyncMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content=sc_json))
        ]
        mock_client.chat.completions.create.return_value = mock_response

        service = SuggestionService(api_key="test_key")
        suggestions = await service.generate_suggestions("query", "answer", [])

        # Expected Traditional Chinese (Taiwan variant)
        # Note: "为什么" -> "為什麼", "讨厌" -> "討厭", "特点" -> "特點", "怎么" -> "怎麼"
        assert "賈寶玉為什麼討厭四書五經？" in suggestions
        assert "林黛玉的性格特點是什麼？" in suggestions
        assert "大觀園是怎麼建成的？" in suggestions
        assert len(suggestions) == 3

@pytest.mark.asyncio
async def test_suggestion_mixed_language_conversion():
    # Test that mixed Simplified and Traditional Chinese are correctly converted
    with patch('src.main.python.services.suggestion_service.AsyncOpenAI') as mock_openai:
        mock_client = mock_openai.return_value
        mock_client.chat.completions.create = AsyncMock()
        
        # Mixed content
        mixed_json = '{"suggestions": ["賈寶玉为什么讨厌四書五經？", "林黛玉的性格特点是什麼？"]}'
        mock_response = AsyncMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content=mixed_json))
        ]
        mock_client.chat.completions.create.return_value = mock_response
        
        service = SuggestionService(api_key="test_key")
        suggestions = await service.generate_suggestions("query", "answer", [])
        
        assert "賈寶玉為什麼討厭四書五經？" in suggestions
        assert "林黛玉的性格特點是什麼？" in suggestions

@pytest.mark.asyncio
async def test_suggestion_idempotency():
    # Test that Traditional Chinese remains unchanged
    with patch('src.main.python.services.suggestion_service.AsyncOpenAI') as mock_openai:
        mock_client = mock_openai.return_value
        mock_client.chat.completions.create = AsyncMock()
        
        tc_json = '{"suggestions": ["賈府的興衰史？", "大觀園的象徵意義？"]}'
        mock_response = AsyncMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content=tc_json))
        ]
        mock_client.chat.completions.create.return_value = mock_response
        
        service = SuggestionService(api_key="test_key")
        suggestions = await service.generate_suggestions("query", "answer", [])
        
        assert "賈府的興衰史？" in suggestions
        assert "大觀園的象徵意義？" in suggestions
