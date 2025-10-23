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
from .sample_widget import render_weather_widget, weather_widget_copy_text, render_nav_button_widget, nav_button_copy_text, NavButtonData
# Removed docs widget imports
from .cekat_docs_memory import get_cekat_docs_rag


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
    """Search Cekat documentation using RAG system with Supabase pgvector."""
    session_id = ctx.context.thread.id
    print("[CekatDocsRAG] tool invoked", {"query": query, "session_id": session_id})
    
    try:
        # Get RAG instance
        rag = get_cekat_docs_rag()
        
        # Search for relevant documents - get top 10
        results = rag.search_docs(query, limit=10)
        
        if results:
            # Format results for the AI
            formatted_results = []
            for doc in results:
                formatted_results.append({
                    "title": doc.get("title", "Untitled"),
                    "content": doc.get("content", ""),
                    "url": doc.get("url", ""),
                    "category": doc.get("category", ""),
                    "similarity": doc.get("similarity", 0)
                })
            
            print("[CekatDocsRAG] search succeeded", {"result_count": len(formatted_results)})
            
            return {
                "query": query,
                "results": formatted_results,
                "status": "success"
            }
        else:
            print("[CekatDocsRAG] no results found")
            return {
                "query": query,
                "results": [],
                "status": "no_results"
            }
            
    except Exception as exc:
        print("[CekatDocsRAG] search failed", {"error": str(exc)})
        return {
            "query": query,
            "results": [],
            "status": "error",
            "error": str(exc)
        }


@function_tool(
    description_override="Convert Cekat documentation search results into a structured documentation widget. Use this after match_cekat_docs_v1 to display search results in a visually appealing format."
)
async def create_cekat_docs_widget_from_results(
    ctx: RunContextWrapper[FactAgentContext],
    query: str,
    results: str,  # JSON string of results
    status: str = "success"
) -> dict[str, str | None]:
    """Convert Cekat docs search results into a documentation widget."""
    print("[CekatDocsWidget] tool invoked", {"query": query, "status": status})
    
    try:
        import json
        
        # Parse results from JSON string
        try:
            results_list = json.loads(results) if isinstance(results, str) else results
        except (json.JSONDecodeError, TypeError):
            results_list = []
        
        if status == "success" and results_list:
            # Format content for the widget with better structure
            widget_content = f"🔍 Menemukan {len(results_list)} hasil untuk '{query}':\n\n"
            
            for i, doc in enumerate(results_list[:3], 1):  # Limit to top 3 for better readability
                title = doc.get("title", "Untitled")
                content = doc.get("content", "")
                url = doc.get("url", "")
                category = doc.get("category", "")
                similarity = doc.get("similarity", 0)
                
                # Truncate content if too long
                if len(content) > 200:
                    content = content[:200] + "..."
                
                # Format with emojis and better structure
                widget_content += f"📄 {title}\n"
                if category:
                    widget_content += f"   🏷️ {category}\n"
                widget_content += f"   📝 {content}\n"
                widget_content += f"   ⭐ Relevansi: {similarity:.1f}\n\n"
            
            # Create widget data
            widget_data_obj = DocsWidgetData(
                title=f"Dokumentasi Cekat: {query}",
                content=widget_content,
                url_link="https://chat.cekat.ai/docs",
                hint="Cekat Documentation",
                feature_type="Documentation"
            )
            
        elif status == "no_results":
            # Create widget for no results
            widget_content = f"🔍 Tidak ada hasil ditemukan untuk '{query}'\n\n"
            widget_content += "💡 Saran:\n"
            widget_content += "• Coba kata kunci yang berbeda\n"
            widget_content += "• Gunakan istilah yang lebih umum\n"
            widget_content += "• Periksa ejaan kata kunci"
            
            widget_data_obj = DocsWidgetData(
                title=f"Pencarian: {query}",
                content=widget_content,
                url_link="https://chat.cekat.ai/docs",
                hint="Cekat Documentation",
                feature_type="Documentation"
            )
            
        else:  # error case
            # Create error widget
            error_msg = "Unknown error"
            if results_list and isinstance(results_list, list) and len(results_list) > 0:
                error_msg = results_list[0].get("error", "Unknown error")
            
            widget_content = f"❌ Error saat mencari '{query}'\n\n"
            widget_content += f"🔧 Detail error: {error_msg}\n\n"
            widget_content += "🆘 Solusi:\n"
            widget_content += "• Coba lagi dalam beberapa saat\n"
            widget_content += "• Periksa koneksi internet\n"
            widget_content += "• Hubungi support jika masalah berlanjut"
            
            widget_data_obj = DocsWidgetData(
                title=f"Error: {query}",
                content=widget_content,
                url_link="https://chat.cekat.ai/docs",
                hint="Cekat Documentation",
                feature_type="Documentation"
            )
        
        # Render the widget
        widget = render_docs_widget(widget_data_obj)
        copy_text = docs_widget_copy_text(widget_data_obj)
        
        # Stream the widget to the client (same as weather widget)
        print("[CekatDocsWidget] streaming widget")
        try:
            await ctx.context.stream_widget(widget, copy_text=copy_text)
        except Exception as exc:
            print("[CekatDocsWidget] widget stream failed", {"error": str(exc)})
            raise ValueError("Documentation widget failed to stream.") from exc
        
        print("[CekatDocsWidget] widget streamed")
        
        print("[CekatDocsWidget] widget created successfully")
        
        return {
            "query": query,
            "results_count": len(results_list) if results_list else 0,
            "status": status,
            "widget_created": "true"
        }
        
    except Exception as exc:
        print("[CekatDocsWidget] error creating widget", {"error": str(exc)})
        return {
            "query": query,
            "status": "error",
            "error": str(exc),
            "widget_created": "false"
        }


@function_tool(
    description_override="Create a navigation button widget for URLs. This creates a beautiful button that users can click to navigate to a page, instead of directly opening a new tab."
)
async def navigate_to_url(
    ctx: RunContextWrapper[FactAgentContext],
    url: str,
    title: str = "",
    description: str = "",
    button_text: str = "Buka Halaman",
    icon: str = "🔗"
) -> dict[str, str | None]:
    """Create a navigation button widget for URLs."""
    print("[NavigateTool] creating navigation button widget", {"url": url, "title": title})
    
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
    
    # Generate title and description if not provided
    if not title:
        # Extract page name from URL
        page_name = url.split('/')[-1] or url.split('/')[-2]
        title = f"Buka {page_name.replace('-', ' ').title()}"
    
    if not description:
        description = f"Klik tombol di bawah untuk membuka halaman {title.lower()}"
    
    try:
        # Create navigation button widget data
        nav_data = NavButtonData(
            title=title,
            description=description,
            url=url,
            button_text=button_text,
            icon=icon
        )
        
        # Render the widget
        widget = render_nav_button_widget(nav_data)
        copy_text = nav_button_copy_text(nav_data)
        
        # Stream the widget to the client
        print("[NavigateTool] streaming navigation button widget")
        try:
            await ctx.context.stream_widget(widget, copy_text=copy_text)
        except Exception as exc:
            print("[NavigateTool] widget stream failed", {"error": str(exc)})
            raise ValueError("Navigation button widget failed to stream.") from exc
        
        print("[NavigateTool] navigation button widget streamed")
        
        return {
            "url": url,
            "title": title,
            "description": description,
            "status": "success",
            "widget_created": "true"
        }
    except Exception as exc:
        print("[NavigateTool] navigation button creation failed", {"error": str(exc)})
        return {
            "url": url,
            "status": "error",
            "error": str(exc),
            "widget_created": "false"
        }




# Export all tools for easy importing
__all__ = [
    "save_fact",
    "switch_theme", 
    "get_weather",
    "match_cekat_docs_v1",
    "navigate_to_url",
    "create_prompt_tool",
    "FactAgentContext",
]
