"""ChatKit server implementation."""

import inspect
import logging
from datetime import datetime
from typing import Any, AsyncIterator
from uuid import uuid4

from agents import Agent, Runner
from chatkit.agents import stream_agent_response
from chatkit.server import ChatKitServer
from chatkit.types import (
    Attachment,
    ClientToolCallItem,
    HiddenContextItem,
    ThreadItem,
    ThreadMetadata,
    ThreadStreamEvent,
    UserMessageItem,
)
from openai.types.responses import ResponseInputImageParam, ResponseInputFileParam

from .attachment_converter import CustomThreadItemConverter
from .tools import (
    FactAgentContext,
    save_fact,
    switch_theme,
    get_weather,
    match_cekat_docs_v1,
# Removed docs widget import
    navigate_to_url,
)
from .agent_prompt import create_prompt_tool
from .constants import INSTRUCTIONS, MODEL
from .memory_store import MemoryStore
from .session_context import session_manager


# If you want to check what's going on under the hood, set this to DEBUG
logging.basicConfig(level=logging.INFO)


def _gen_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:8]}"


def _is_tool_completion_item(item: Any) -> bool:
    return isinstance(item, ClientToolCallItem)


def _user_message_text(item: UserMessageItem) -> str:
    parts: list[str] = []
    for part in item.content:
        text = getattr(part, "text", None)
        if text:
            parts.append(text)
    return " ".join(parts).strip()


class FactAssistantServer(ChatKitServer[dict[str, Any]]):
    """ChatKit server wired up with the fact-recording tool."""

    def __init__(self, attachment_store=None) -> None:
        self.store: MemoryStore = MemoryStore()
        super().__init__(self.store, attachment_store=attachment_store)
        tools = [save_fact, switch_theme, get_weather, match_cekat_docs_v1, navigate_to_url, create_prompt_tool]
        self.assistant = Agent[FactAgentContext](
            model=MODEL,
            name="ChatKit Guide",
            instructions=INSTRUCTIONS,
            tools=tools,  # type: ignore[arg-type]
        )
        self._thread_item_converter = self._init_thread_item_converter()

    async def respond(
        self,
        thread: ThreadMetadata,
        item: UserMessageItem | None,
        context: dict[str, Any],
    ) -> AsyncIterator[ThreadStreamEvent]:
        print(f"[DEBUG] Server respond called with item: {type(item).__name__ if item else None}")
        if item:
            print(f"[DEBUG] Item content: {item.content}")
            print(f"[DEBUG] Item attributes: {dir(item)}")
        
        # Session context management
        session_id = thread.id
        if item:
            # Extract user message content
            user_content = _user_message_text(item)
            session_manager.add_user_message(session_id, user_content)
            
            # Get conversation context
            conversation_context = session_manager.get_session_context(session_id, max_turns=5)
            print(f"📝 Session Context:\n{conversation_context}")
        
        agent_context = FactAgentContext(
            thread=thread,
            store=self.store,
            request_context=context,
        )

        target_item: ThreadItem | None = item
        if target_item is None:
            target_item = await self._latest_thread_item(thread, context)

        if target_item is None or _is_tool_completion_item(target_item):
            return

        agent_input = await self._to_agent_input(thread, target_item)
        if agent_input is None:
            return

        # Use the converter to get proper input format for Agent SDK
        converter = CustomThreadItemConverter()
        proper_input = await converter.to_agent_input(target_item, thread)
        
        # If converter returns None, use the original agent_input
        if proper_input is not None:
            agent_input = proper_input

        # Inject session context into agent input
        if item and session_id in session_manager.sessions:
            conversation_context = session_manager.get_session_context(session_id, max_turns=5)
            if conversation_context and "CONVERSATION CONTEXT" in conversation_context:
                # agent_input is a string, so we can directly prepend context
                if isinstance(agent_input, str):
                    original_content = agent_input
                    agent_input = f"{conversation_context}\n\n{original_content}"
                    print(f"🔄 Injected session context into AI prompt")
                else:
                    print(f"🔍 Unexpected agent_input type: {type(agent_input)}")

        result = Runner.run_streamed(
            self.assistant,
            agent_input,
            context=agent_context,
        )

        # Track assistant response
        assistant_response_parts = []
        tool_calls_used = []
        
        async for event in stream_agent_response(agent_context, result):
            # Track assistant response content
            if hasattr(event, 'content') and event.content:
                assistant_response_parts.append(str(event.content))
            
            # Track tool calls
            if hasattr(event, 'tool_call') and event.tool_call:
                tool_calls_used.append({
                    'name': getattr(event.tool_call, 'name', 'unknown'),
                    'arguments': getattr(event.tool_call, 'arguments', {})
                })
            
            yield event
        
        # Save assistant response to session context
        if assistant_response_parts and item:
            assistant_content = " ".join(assistant_response_parts).strip()
            if assistant_content:
                session_manager.add_assistant_message(
                    session_id, 
                    assistant_content, 
                    tool_calls=tool_calls_used if tool_calls_used else None
                )
                print(f"🤖 Saved assistant response to session {session_id}")
        
        return

    async def action(
        self,
        thread: ThreadMetadata,
        action: dict[str, Any],
        context: dict[str, Any],
        *args: Any,
        **kwargs: Any,
    ) -> AsyncIterator[ThreadStreamEvent]:
        """Handle widget actions like button clicks."""
        print(f"[DEBUG] Action received: {action}")
        print(f"[DEBUG] Action type: {type(action)}")
        print(f"[DEBUG] Thread: {thread}")
        print(f"[DEBUG] Context: {context}")
        print(f"[DEBUG] Args: {args}")
        print(f"[DEBUG] Kwargs: {kwargs}")
        
        # Action is an Action object, not a dict
        action_type = getattr(action, 'type', None)
        payload = getattr(action, 'payload', {})
        
        print(f"[DEBUG] Action type: {action_type}")
        print(f"[DEBUG] Payload: {payload}")
        
        if action_type == "navigation.open":
            url = payload.get("url") if isinstance(payload, dict) else getattr(payload, 'url', None)
            if url:
                print(f"[DEBUG] Navigation action: Opening URL {url}")
                # For now, just log the action
                # Frontend onAction callback will handle the navigation
                pass
        
        # Return empty iterator for other actions
        return
        yield  # This line will never be reached, but needed for async generator

    async def to_message_content(self, _input: Attachment) -> ResponseInputImageParam | ResponseInputFileParam:
        """Convert attachment to message content for ChatKit."""
        # Delegate to CustomThreadItemConverter
        converter = CustomThreadItemConverter()
        return await converter.attachment_to_message_content(_input)

    def _init_thread_item_converter(self) -> Any | None:
        """Initialize custom ThreadItemConverter untuk handle attachments."""
        try:
            return CustomThreadItemConverter()
        except Exception as e:
            print(f"[ERROR] Failed to initialize custom converter: {e}")
            return None

    async def _latest_thread_item(
        self, thread: ThreadMetadata, context: dict[str, Any]
    ) -> ThreadItem | None:
        try:
            items = await self.store.load_thread_items(thread.id, None, 1, "desc", context)
        except Exception:  # pragma: no cover - defensive
            return None

        return items.data[0] if getattr(items, "data", None) else None

    async def _to_agent_input(
        self,
        thread: ThreadMetadata,
        item: ThreadItem,
    ) -> Any | None:
        if _is_tool_completion_item(item):
            return None

        converter = getattr(self, "_thread_item_converter", None)
        if converter is not None:
            # Try our custom to_agent_input method first
            if hasattr(converter, 'to_agent_input'):
                try:
                    result = await converter.to_agent_input(item, thread)
                    if result is not None:
                        return result
                except Exception as e:
                    print(f"[ERROR] Custom converter failed: {e}")
            
            # Fallback to original method discovery
            for attr in (
                "to_input_item",
                "convert",
                "convert_item",
                "convert_thread_item",
            ):
                method = getattr(converter, attr, None)
                if method is None:
                    continue
                call_args: list[Any] = [item]
                call_kwargs: dict[str, Any] = {}
                try:
                    signature = inspect.signature(method)
                except (TypeError, ValueError):
                    signature = None

                if signature is not None:
                    params = [
                        parameter
                        for parameter in signature.parameters.values()
                        if parameter.kind
                        not in (
                            inspect.Parameter.VAR_POSITIONAL,
                            inspect.Parameter.VAR_KEYWORD,
                        )
                    ]
                    if len(params) >= 2:
                        next_param = params[1]
                        if next_param.kind in (
                            inspect.Parameter.POSITIONAL_ONLY,
                            inspect.Parameter.POSITIONAL_OR_KEYWORD,
                        ):
                            call_args.append(thread)
                        else:
                            call_kwargs[next_param.name] = thread

                result = method(*call_args, **call_kwargs)
                if inspect.isawaitable(result):
                    return await result
                return result

        if isinstance(item, UserMessageItem):
            return _user_message_text(item)

        return None

    async def _add_hidden_item(
        self,
        thread: ThreadMetadata,
        context: dict[str, Any],
        content: str,
    ) -> None:
        await self.store.add_thread_item(
            thread.id,
            HiddenContextItem(
                id=_gen_id("msg"),
                thread_id=thread.id,
                created_at=datetime.now(),
                content=content,
            ),
            context,
        )


def create_chatkit_server(attachment_store=None) -> FactAssistantServer | None:
    """Return a configured ChatKit server instance if dependencies are available."""
    return FactAssistantServer(attachment_store)
