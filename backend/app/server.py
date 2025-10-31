"""ChatKit server implementation."""

import inspect
import logging
from datetime import datetime
from typing import Any, AsyncIterator
from uuid import uuid4

from agents import Agent, Runner, WebSearchTool, ModelSettings, RunConfig
try:
    from agents import ImageGenerationTool
    from openai.types.responses.tool_param import ImageGeneration
    HAS_IMAGE_GENERATION = True
except ImportError:
    HAS_IMAGE_GENERATION = False
    ImageGenerationTool = None
    ImageGeneration = None
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
from openai import max_retries
from openai.types.responses import ResponseInputImageParam, ResponseInputFileParam
from openai.types.shared import reasoning, reasoning_effort

from .attachment_converter import CustomThreadItemConverter
from .tools import (
    FactAgentContext,
    save_fact,
    switch_theme,
    get_weather,
    match_cekat_docs_v1,
# Removed docs widget import
    navigate_to_url,
    generate_image,
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
        # Build tools list
        tools = [WebSearchTool(), match_cekat_docs_v1, create_prompt_tool, generate_image, navigate_to_url]
        
        # Add ImageGenerationTool if available (for partial_images support)
        if HAS_IMAGE_GENERATION:
            tools.append(ImageGenerationTool(
                tool_config=ImageGeneration(
                    type="image_generation",
                    model="gpt-image-1-mini",
                    quality="low",
                    size="1024x1024",
                    partial_images=1, 
                ),
            ))
        
        # Disable tracing for performance - set environment variable
        import os
        os.environ['OPENAI_TRACING_DISABLED'] = 'true'
        
        self.assistant = Agent[FactAgentContext](
            model=MODEL,
            name="ChatKit Guide",
            instructions=INSTRUCTIONS,
        
            tools=tools,  # type: ignore[arg-type
        )
        self._thread_item_converter = self._init_thread_item_converter()

    async def respond(
        self,
        thread: ThreadMetadata,
        item: UserMessageItem | None,
        context: dict[str, Any],
    ) -> AsyncIterator[ThreadStreamEvent]:
        # Debug logging - log user request
        if item:
            user_content = _user_message_text(item)
            print(f"👤 [USER REQUEST] {user_content}")
        
        # Session context management
        session_id = thread.id
        conversation_context = None
        
        if item:
            # Extract user message content
            user_content = _user_message_text(item)
            session_manager.add_user_message(session_id, user_content)
        
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

        # Inject session context into agent input - reduced to 1 for fastest processing
        if item and session_id in session_manager.sessions:
            conversation_context = session_manager.get_session_context(session_id, max_turns=2)
            if conversation_context and "CONVERSATION CONTEXT" in conversation_context:
                # agent_input is a string, so we can directly prepend context
                if isinstance(agent_input, str):
                    original_content = agent_input
                    agent_input = f"{conversation_context}\n\n{original_content}"
                    # Session context injected silently for performance
                else:
                    print(f"🔍 Unexpected agent_input type: {type(agent_input)}")

        # Track request timing
        import time
        request_start = time.time()
        
        result = Runner.run_streamed(
            self.assistant,
            agent_input,
            context=agent_context,
            max_turns=3,  # Limit to 3 turns for speed
            run_config=RunConfig(
                model_settings=ModelSettings(       
                    reasoning={"effort": "low"},
                )
            )
        )

        # Track assistant response
        assistant_response_parts = []
        tool_calls_used = []
        assistant_content = ""
        
        turn_count = 0
        image_generation_called = False
        
        async for event in stream_agent_response(agent_context, result):
            # Track image generation events - log EVERY event type for debugging
            event_type = type(event).__name__
            
            # Check for tool call events
            if hasattr(event, 'tool_call') and event.tool_call:
                tool_name = getattr(event.tool_call, 'name', 'unknown')
                tool_args = getattr(event.tool_call, 'arguments', {})
                print(f"🔧 [SERVER] Tool call detected: {tool_name}")
                print(f"🔧 [SERVER] Tool arguments: {tool_args}")
                if tool_name == 'image_generation' or tool_name == 'generate_image':
                    image_generation_called = True
                    print(f"🖼️ [SERVER] Image generation tool triggered!")
            
            # Track assistant response content from ThreadItemUpdated
            if hasattr(event, 'item') and event.item and hasattr(event.item, 'content'):
                # Extract text content from item
                for block in event.item.content:
                    if hasattr(block, 'text') and block.text:
                        content_str = block.text
                        assistant_response_parts.append(content_str)
                        assistant_content += content_str + " "
            
            # Track tool calls
            if hasattr(event, 'tool_call') and event.tool_call:
                tool_name = getattr(event.tool_call, 'name', 'unknown')
                tool_args = getattr(event.tool_call, 'arguments', {})
                print(f"📋 [SERVER] Tracking tool call: {tool_name}")
                tool_calls_used.append({
                    'name': tool_name,
                    'arguments': tool_args
                })
                turn_count += 1
                
            
            yield event
        
        # Build assistant content from parts
        if assistant_response_parts and item:
            assistant_content = " ".join(assistant_response_parts).strip()
            
            # Content already processed above
            if assistant_content:
                # Logging removed for performance
                session_manager.add_assistant_message(
                    session_id, 
                    assistant_content, 
                    tool_calls=tool_calls_used if tool_calls_used else None
                )
        
        # Stream navigation widget AFTER text response completes
        navigate_url_info = agent_context.request_context.get('navigate_url_info')
        if navigate_url_info and item:
            from .sample_widget import render_nav_button_widget, nav_button_copy_text, NavButtonData
            from chatkit.server import stream_widget
            
            try:
                url = navigate_url_info.get('url', '')
                page_name = url.split('/')[-1] or url.split('/')[-2]
                page_title = page_name.replace('-', ' ').title()
                
                widget_data = NavButtonData(
                    title=page_title,
                    description=navigate_url_info.get('description', ''),
                    button_text=navigate_url_info.get('link_text', 'Buka Halaman'),
                    url=url,
                    icon="🔗"
                )
                widget = render_nav_button_widget(widget_data)
                copy_text = nav_button_copy_text(widget_data)
                
                print(f"🔄 [SERVER] Streaming navigation widget for: {url}")
                # Stream widget events AFTER text response
                async for widget_event in stream_widget(thread, widget, copy_text=copy_text):
                    yield widget_event
                print(f"✅ [SERVER] Navigation widget streamed")
            except Exception as e:
                print(f"❌ [SERVER] Failed to stream widget: {e}")
        
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
        # Debug logging removed for performance
        
        # Action is an Action object, not a dict
        action_type = getattr(action, 'type', None)
        payload = getattr(action, 'payload', {})
        
        if action_type == "navigation.open":
            url = payload.get("url") if isinstance(payload, dict) else getattr(payload, 'url', None)
            if url:
                # Navigation handled by frontend
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
