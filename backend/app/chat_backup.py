"""ChatKit server integration for the boilerplate backend."""

from __future__ import annotations
import inspect
import logging
from datetime import datetime
from typing import Annotated, Any, AsyncIterator, Final, Literal
from uuid import uuid4

from agents import Agent, RunContextWrapper, Runner, function_tool
from chatkit.agents import (
    AgentContext,
    ClientToolCall,
    ThreadItemConverter,
    stream_agent_response,
)
from chatkit.server import ChatKitServer, ThreadItemDoneEvent
from chatkit.types import (
    Attachment,
    ClientToolCallItem,
    HiddenContextItem,
    ImageAttachment,
    ThreadItem,
    ThreadMetadata,
    ThreadStreamEvent,
    UserMessageItem,
)

from openai.types.responses import ResponseInputImageParam, ResponseInputFileParam
from pydantic import ConfigDict, Field

from .constants import INSTRUCTIONS, MODEL
from .facts import Fact, fact_store
from .memory_store import MemoryStore
from .sample_widget import render_weather_widget, weather_widget_copy_text
from .weather import (
    WeatherLookupError,
    retrieve_weather,
)
from .weather import (
    normalize_unit as normalize_temperature_unit,
)
from .cekat_docs_memory import search_cekat_docs

# If you want to check what's going on under the hood, set this to DEBUG
logging.basicConfig(level=logging.INFO)

async def read_attachment_bytes(attachment_id: str) -> bytes:
    """Replace with your blob-store fetch (S3, local disk, etc.)."""
    from .main import attachment_store
    return await attachment_store.get_attachment_bytes(attachment_id)

class CustomThreadItemConverter(ThreadItemConverter):
    """Custom ThreadItemConverter untuk handle attachments dengan benar."""
    
    async def attachment_to_message_content(self, input: Attachment) -> ResponseInputImageParam | ResponseInputFileParam:
        """Convert attachment to message content sesuai dokumentasi ChatKit."""
        import base64
        
        try:
            # Get attachment bytes menggunakan helper function
            content = await read_attachment_bytes(input.id)
            
            # Create data URL
            data = (
                "data:"
                + str(input.mime_type)
                + ";base64,"
                + base64.b64encode(content).decode("utf-8")
            )
            
            # Return sesuai type attachment menggunakan isinstance
            if isinstance(input, ImageAttachment):
                return ResponseInputImageParam(
                    type="input_image",
                    detail="auto",
                    image_url=data,
                )
            else:
                # Note: Agents SDK currently only supports pdf files as ResponseInputFileParam.
                # To send other text file types, either convert them to pdf on the fly or
                # add them as input text.
                return ResponseInputFileParam(
                    type="input_file",
                    file_data=data,
                    filename=input.name or "unknown",
                )
                
        except Exception as e:
            print(f"[ERROR] Failed to convert attachment: {e}")
            # Fallback ke text description
            return ResponseInputFileParam(
                type="input_file",
                file_data=f"📎 Attachment: {input.name or 'Unknown file'} (failed to load)",
                filename=input.name or "unknown",
            )
    
    async def to_agent_input(self, item: ThreadItem, thread: ThreadMetadata) -> Any | None:
        """Convert ThreadItem to agent input, handling attachments properly."""
        print(f"[DEBUG] Converting ThreadItem: {type(item).__name__}")
        
        if isinstance(item, UserMessageItem):
            print(f"[DEBUG] Processing UserMessageItem with {len(item.content)} content parts")
            
            # Extract text content
            text_parts = []
            attachment_contents = []
            
            # Process each content part
            for i, part in enumerate(item.content):
                print(f"[DEBUG] Processing content part {i}: {type(part).__name__}")
                
                if hasattr(part, 'text') and part.text:
                    text_parts.append(part.text)
                    print(f"[DEBUG] Added text: {part.text[:50]}...")
                elif hasattr(part, 'attachment') and part.attachment:
                    print(f"[DEBUG] Found attachment: {part.attachment.id}, type: {part.attachment.mime_type}")
                    # Convert attachment to message content
                    try:
                        attachment_content = await self.attachment_to_message_content(part.attachment)
                        attachment_contents.append(attachment_content)
                        print(f"[DEBUG] Successfully converted attachment {part.attachment.id} to content")
                    except Exception as e:
                        print(f"[ERROR] Failed to convert attachment: {e}")
                        import traceback
                        traceback.print_exc()
                        # Add fallback text
                        text_parts.append(f"[Attachment: {part.attachment.name or 'Unknown file'}]")
            
            print(f"[DEBUG] Final result - text_parts: {len(text_parts)}, attachment_contents: {len(attachment_contents)}")
            
            # Combine text and attachments
            if text_parts and attachment_contents:
                # Return both text and attachments
                result = {
                    "text": " ".join(text_parts).strip(),
                    "attachments": attachment_contents
                }
                print(f"[DEBUG] Returning combined result: {result}")
                return result
            elif attachment_contents:
                # Only attachments, no text
                result = {
                    "text": "",
                    "attachments": attachment_contents
                }
                print(f"[DEBUG] Returning attachments only: {result}")
                return result
            elif text_parts:
                # Only text, no attachments
                result = " ".join(text_parts).strip()
                print(f"[DEBUG] Returning text only: {result}")
                return result
            else:
                # Empty message
                print(f"[DEBUG] Returning empty message")
                return ""
        
        # For other types, return None to use default handling
        print(f"[DEBUG] Returning None for {type(item).__name__}")
        return None

SUPPORTED_COLOR_SCHEMES: Final[frozenset[str]] = frozenset({"light", "dark"})
CLIENT_THEME_TOOL_NAME: Final[str] = "switch_theme"


def _normalize_color_scheme(value: str) -> str:
    normalized = str(value).strip().lower()
    if normalized in SUPPORTED_COLOR_SCHEMES:
        return normalized
    if "dark" in normalized:
        return "dark"
    if "light" in normalized:
        return "light"
    raise ValueError("Theme must be either 'light' or 'dark'.")


def _gen_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:8]}"


def _is_tool_completion_item(item: Any) -> bool:
    return isinstance(item, ClientToolCallItem)


class FactAgentContext(AgentContext):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    store: Annotated[MemoryStore, Field(exclude=True)]
    request_context: dict[str, Any]


async def _stream_saved_hidden(ctx: RunContextWrapper[FactAgentContext], fact: Fact) -> None:
    await ctx.context.stream(
        ThreadItemDoneEvent(
            item=HiddenContextItem(
                id=_gen_id("msg"),
                thread_id=ctx.context.thread.id,
                created_at=datetime.now(),
                content=(
                    f'<FACT_SAVED id="{fact.id}" threadId="{ctx.context.thread.id}">{fact.text}</FACT_SAVED>'
                ),
            ),
        )
    )


@function_tool(description_override="Record a fact shared by the user so it is saved immediately.")
async def save_fact(
    ctx: RunContextWrapper[FactAgentContext],
    fact: str,
) -> dict[str, str] | None:
    try:
        saved = await fact_store.create(text=fact)
        confirmed = await fact_store.mark_saved(saved.id)
        if confirmed is None:
            raise ValueError("Failed to save fact")
        await _stream_saved_hidden(ctx, confirmed)
        ctx.context.client_tool_call = ClientToolCall(
            name="record_fact",
            arguments={"fact_id": confirmed.id, "fact_text": confirmed.text},
        )
        print(f"FACT SAVED: {confirmed}")
        return {"fact_id": confirmed.id, "status": "saved"}
    except Exception:
        logging.exception("Failed to save fact")
        return None


@function_tool(
    description_override="Switch the chat interface between light and dark color schemes."
)
async def switch_theme(
    ctx: RunContextWrapper[FactAgentContext],
    theme: str,
) -> dict[str, str] | None:
    logging.debug(f"Switching theme to {theme}")
    try:
        requested = _normalize_color_scheme(theme)
        ctx.context.client_tool_call = ClientToolCall(
            name=CLIENT_THEME_TOOL_NAME,
            arguments={"theme": requested},
        )
        return {"theme": requested}
    except Exception:
        logging.exception("Failed to switch theme")
        return None


@function_tool(
    description_override="Look up the current weather and upcoming forecast for a location and render an interactive weather dashboard."
)
async def get_weather(
    ctx: RunContextWrapper[FactAgentContext],
    location: str,
    unit: Literal["celsius", "fahrenheit"] | str | None = None,
) -> dict[str, str | None]:
    print("[WeatherTool] tool invoked", {"location": location, "unit": unit})
    try:
        normalized_unit = normalize_temperature_unit(unit)
    except WeatherLookupError as exc:
        print("[WeatherTool] invalid unit", {"error": str(exc)})
        raise ValueError(str(exc)) from exc

    try:
        data = await retrieve_weather(location, normalized_unit)
    except WeatherLookupError as exc:
        print("[WeatherTool] lookup failed", {"error": str(exc)})
        raise ValueError(str(exc)) from exc

    print(
        "[WeatherTool] lookup succeeded",
        {
            "location": data.location,
            "temperature": data.temperature,
            "unit": data.temperature_unit,
        },
    )
    try:
        widget = render_weather_widget(data)
        copy_text = weather_widget_copy_text(data)
        payload: Any
        try:
            payload = widget.model_dump()
        except AttributeError:
            payload = widget
        print("[WeatherTool] widget payload", payload)
    except Exception as exc:  # noqa: BLE001
        print("[WeatherTool] widget build failed", {"error": str(exc)})
        raise ValueError("Weather data is currently unavailable for that location.") from exc

    print("[WeatherTool] streaming widget")
    try:
        await ctx.context.stream_widget(widget, copy_text=copy_text)
    except Exception as exc:  # noqa: BLE001
        print("[WeatherTool] widget stream failed", {"error": str(exc)})
        raise ValueError("Weather data is currently unavailable for that location.") from exc

    print("[WeatherTool] widget streamed")

    observed = data.observation_time.isoformat() if data.observation_time else None

    return {
        "location": data.location,
        "unit": normalized_unit,
        "observed_at": observed,
    }


@function_tool(
    description_override="MANDATORY TOOL: Gunakan tool ini untuk SEMUA pertanyaan yang berkaitan dengan Cekat, CekatAI, atau Cekat AI. Tool ini mencari informasi dokumen Cekat menggunakan sistem pencarian semantik. WAJIB digunakan untuk menjawab pertanyaan tentang fitur, cara penggunaan, dokumentasi, atau apapun yang berkaitan dengan Cekat. Trigger words: Cekat, CekatAI, platform, features, integration, API, documentation, setup, configuration, AI Agent, chatbot, omnichannel, CRM, webhook, automation."
)
async def match_cekat_docs_v1(
    ctx: RunContextWrapper[FactAgentContext],
    query: str,
) -> dict[str, str | None]:
    """Mencari dokumen Cekat menggunakan webhook n8n."""
    # Ambil sessionId dari thread context
    session_id = ctx.context.thread.id
    print("[CekatDocsTool] tool invoked", {"query": query, "session_id": session_id})
    try:
        result = search_cekat_docs(query, session_id)
        print("[CekatDocsTool] search succeeded", {"result_length": len(result)})
        
        return {
            "query": query,
            "result": result,
            "status": "success"
        }
    except Exception as exc:
        print("[CekatDocsTool] search failed", {"error": str(exc)})
        return {
            "query": query,
            "result": f"Error mencari dokumen: {str(exc)}",
            "status": "error"
        }


@function_tool(
    description_override="Navigasi ke halaman Cekat atau URL tertentu. Gunakan tool ini untuk membuka dashboard, conversation, tickets, workflows, atau halaman Cekat lainnya. Mendukung hardcoded URLs untuk halaman Cekat yang umum."
)
async def navigate_to_url(
    ctx: RunContextWrapper[FactAgentContext],
    url: str,
    open_in_new_tab: bool = True,
    description: str = "",
) -> dict[str, str | None]:
    """Navigasi ke URL atau buka tab baru dengan hardcoded Cekat URLs."""
    print("[NavigateTool] tool invoked", {"url": url, "open_in_new_tab": open_in_new_tab})
    
    # Hardcoded Cekat URLs mapping
    cekat_urls = {
        "conversation": "https://chat.cekat.ai/chat",
        "conversations": "https://chat.cekat.ai/chat",
        "chat": "https://chat.cekat.ai/chat",
        "tickets": "https://chat.cekat.ai/tickets",
        "ticket": "https://chat.cekat.ai/tickets",
        "workflows": "https://chat.cekat.ai/workflows",
        "workflow": "https://chat.cekat.ai/workflows",
        "automation": "https://chat.cekat.ai/workflows",
        "orders": "https://chat.cekat.ai/orders",
        "order": "https://chat.cekat.ai/orders",
        "analytics": "https://chat.cekat.ai/dashboard/analytics",
        "dashboard": "https://chat.cekat.ai/dashboard/analytics",
        "broadcasts": "https://chat.cekat.ai/broadcasts",
        "broadcast": "https://chat.cekat.ai/broadcasts",
        "campaign": "https://chat.cekat.ai/broadcasts",
        "connected-platforms": "https://chat.cekat.ai/connected-platforms",
        "platforms": "https://chat.cekat.ai/connected-platforms",
        "integration": "https://chat.cekat.ai/connected-platforms",
        "chatbots": "https://chat.cekat.ai/chatbots/chatbot-list",
        "chatbot": "https://chat.cekat.ai/chatbots/chatbot-list",
        "ai-agent": "https://chat.cekat.ai/chatbots/chatbot-list",
        "ai-agents": "https://chat.cekat.ai/chatbots/chatbot-list",
        "agent-management": "https://chat.cekat.ai/users/agent-management",
        "agents": "https://chat.cekat.ai/users/agent-management",
        "human-agent": "https://chat.cekat.ai/users/agent-management",
        "products": "https://chat.cekat.ai/products",
        "product": "https://chat.cekat.ai/products",
        "followups": "https://chat.cekat.ai/followups",
        "follow-up": "https://chat.cekat.ai/followups",
        "quick-reply": "https://chat.cekat.ai/quick-reply",
        "quick-replies": "https://chat.cekat.ai/quick-reply",
        "labels": "https://chat.cekat.ai/labels",
        "label": "https://chat.cekat.ai/labels",
        "api-tools": "https://chat.cekat.ai/developers/api-tools",
        "api": "https://chat.cekat.ai/developers/api-tools",
        "developers": "https://chat.cekat.ai/developers/api-tools",
        "documentation": "https://documenter.getpostman.com/view/28427156/2sAXqtagQo",
        "docs": "https://documenter.getpostman.com/view/28427156/2sAXqtagQo",
        "postman": "https://documenter.getpostman.com/view/28427156/2sAXqtagQo",
    }
    
    # Cek apakah URL adalah keyword yang sudah di-mapping
    url_lower = url.lower().strip()
    if url_lower in cekat_urls:
        url = cekat_urls[url_lower]
        print(f"[NavigateTool] Mapped '{url_lower}' to '{url}'")
    
    # Validasi URL
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    
    try:
        ctx.context.client_tool_call = ClientToolCall(
            name="navigate_to_url",
            arguments={
                "url": url,
                "open_in_new_tab": open_in_new_tab,
                "description": description or f"Navigasi ke {url}"
            },
        )
        
        return {
            "url": url,
            "open_in_new_tab": open_in_new_tab,
            "description": description,
            "status": "success"
        }
    except Exception as exc:
        print("[NavigateTool] navigation failed", {"error": str(exc)})
        return {
            "url": url,
            "status": "error",
            "error": str(exc)
        }


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
        tools = [save_fact, switch_theme, get_weather, match_cekat_docs_v1, navigate_to_url]
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

        result = Runner.run_streamed(
            self.assistant,
            agent_input,
            context=agent_context,
        )

        async for event in stream_agent_response(agent_context, result):
            yield event
        return

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
