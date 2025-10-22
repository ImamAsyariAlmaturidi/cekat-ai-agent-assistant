"""Function tools for the ChatKit assistant."""

import logging
from datetime import datetime
from typing import Any, Literal, Union
from uuid import uuid4

from agents import RunContextWrapper, function_tool
from chatkit.agents import AgentContext, ClientToolCall
from openai.types.shared import reasoning_effort
from pydantic import ConfigDict, Field
from typing import Annotated

from .facts import Fact, fact_store
from .weather import (
    WeatherLookupError,
    retrieve_weather,
    normalize_unit as normalize_temperature_unit,
)
from .sample_widget import render_weather_widget, weather_widget_copy_text
from .cekat_docs_memory import search_cekat_docs


def _gen_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:8]}"


def _normalize_color_scheme(value: str) -> str:
    SUPPORTED_COLOR_SCHEMES = frozenset({"light", "dark"})
    normalized = str(value).strip().lower()
    if normalized in SUPPORTED_COLOR_SCHEMES:
        return normalized
    if "dark" in normalized:
        return "dark"
    if "light" in normalized:
        return "light"
    raise ValueError("Theme must be either 'light' or 'dark'.")


class FactAgentContext(AgentContext):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    store: Annotated[Any, Field(exclude=True)]
    request_context: dict[str, Any]



async def _stream_saved_hidden(ctx: RunContextWrapper[FactAgentContext], fact: Fact) -> None:
    from chatkit.server import ThreadItemDoneEvent
    from chatkit.types import HiddenContextItem
    
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
    CLIENT_THEME_TOOL_NAME = "switch_theme"
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
    description_override="Directly navigate to a URL by opening it in a new browser tab. Use this ONLY for direct navigation without creating any widget or button. For creating clickable buttons, use create_url_widget instead."
)
async def navigate_to_url(
    ctx: RunContextWrapper[FactAgentContext],
    url: str,
    description: str = "",
) -> dict[str, str | None]:
    """Navigasi ke URL atau buka tab baru dengan hardcoded Cekat URLs."""
    print("[NavigateTool] tool invoked", {"url": url, "force_new_tab": True})
    
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
                "open_in_new_tab": True,
                "description": description or f"Navigasi ke {url}"
            },
        )
        
        return {
            "url": url,
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


# Export all tools for easy importing
__all__ = [
    "save_fact",
    "switch_theme", 
    "get_weather",
    "match_cekat_docs_v1",
    "navigate_to_url",
    "FactAgentContext",
]
