"""Legacy chat.py - now redirects to refactored modules."""

# This file is kept for backward compatibility
# All functionality has been moved to separate modules:

from .server import FactAssistantServer, create_chatkit_server
from .attachment_converter import CustomThreadItemConverter, read_attachment_bytes
from .tools import (
    FactAgentContext,
    save_fact,
    switch_theme,
    get_weather,
    match_cekat_docs_v1,
    navigate_to_url,
)

# Re-export everything for backward compatibility
__all__ = [
    "FactAssistantServer",
    "create_chatkit_server", 
    "CustomThreadItemConverter",
    "read_attachment_bytes",
    "FactAgentContext",
    "save_fact",
    "switch_theme",
    "get_weather",
    "match_cekat_docs_v1",
    "navigate_to_url",
]
