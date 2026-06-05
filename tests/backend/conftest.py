import pytest
import sys
from unittest.mock import patch, MagicMock

# Patch RAGService before any backend modules are imported
patcher = patch('services.rag_service.RAGService', autospec=True)
MockRAGService = patcher.start()

# We also need to patch the RouterService and SuggestionService if they do heavy lifting
patch('services.router_service.RouterService', autospec=True).start()
patch('services.suggestion_service.SuggestionService', autospec=True).start()

def pytest_unconfigure(config):
    patch.stopall()
