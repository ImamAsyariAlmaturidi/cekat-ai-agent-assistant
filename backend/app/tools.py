"""Function tools for the ChatKit assistant."""

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Literal, Union
from uuid import uuid4

from agents import RunContextWrapper, function_tool, model_settings
from chatkit.agents import AgentContext, ClientToolCall
from openai.types.shared import reasoning, reasoning_effort
from pydantic import ConfigDict, Field
from typing import Annotated
import os
import base64
from openai import AsyncOpenAI, OpenAI, max_retries

from .facts import Fact, fact_store
from .weather import (
    WeatherLookupError,
    retrieve_weather,
    normalize_unit as normalize_temperature_unit,
)
from .sample_widget import (
    render_weather_widget, 
    weather_widget_copy_text,
    ImageGenerationWidgetData,
    render_image_generation_widget,
    image_generation_widget_copy_text
)
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
    description_override="MANDATORY TOOL untuk MENCARI INFORMASI SPESIFIK dari dokumentasi Cekat. PAKAI TOOL INI untuk: 1) User bertanya tentang harga, subscription, paket, plans (Wajib pakai tool!), 2) User bertanya cara membuat, cara setup, cara menggunakan fitur, 3) User butuh info detail technical atau dokumentasi. Tool ini mengambil informasi terkini dari dokumentasi Cekat. JANGAN jawab generic jika user tanya harga/paket - HARUS pakai tool ini!"
)
async def match_cekat_docs_v1(
    ctx: RunContextWrapper[FactAgentContext],
    query: str,
) -> dict[str, str | None]:
    """Search Cekat documentation using RAG system with Supabase pgvector."""
    session_id = ctx.context.thread.id
    start_time = time.time()
    print(f"🔍 [TOOL] match_cekat_docs_v1 started - query: '{query[:50]}'")
    
    try:
        # Get RAG instance
        rag = get_cekat_docs_rag()
        
        # Search for relevant documents - limit to 10 for comprehensive results
        results = rag.search_docs(query, limit=10)
        
        if results:
            # Format results for the AI with truncated content
            formatted_results = []
            for doc in results:
                # Truncate content to prevent huge responses - reduced to 500 for speed
                content = doc.get("content", "")
                if len(content) > 500:  # Limit content to 500 chars
                    content = content[:500] + "..."
                
                formatted_results.append({
                    "title": doc.get("title", "Untitled"),
                    "content": content,
                    "url": doc.get("url", ""),
                    "category": doc.get("category", ""),
                    "similarity": doc.get("similarity", 0)
                })
            
            elapsed = time.time() - start_time
            print(f"✅ [TOOL] match_cekat_docs_v1 completed in {elapsed:.2f}s - Found {len(formatted_results)} results")
            
            return {
                "query": query,
                "results": formatted_results,
                "status": "success"
            }
        else:
            elapsed = time.time() - start_time
            print(f"⚠️ [TOOL] match_cekat_docs_v1 completed in {elapsed:.2f}s - No results found")
            return {
                "query": query,
                "results": [],
                "status": "no_results"
            }
            
    except Exception as exc:
        elapsed = time.time() - start_time
        print(f"❌ [TOOL] match_cekat_docs_v1 failed in {elapsed:.2f}s - Error: {str(exc)[:100]}")
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
    description_override="Use this to enable navigation to Cekat pages when user mentions a feature or asks to access/go to a page. Keywords: workflows, chatbots, broadcast, ai-agent, agent-management, products, orders, analytics, connected-platforms. Use when relevant to the conversation."
)
async def navigate_to_url(
    ctx: RunContextWrapper[FactAgentContext],
    url: str,
    link_text: str = "",
    description: str = ""
) -> dict[str, str | None]:
    """Enable navigation to Cekat pages. MANDATORY to call after answering questions about Cekat features."""
    start_time = time.time()
    print(f"🧭 [TOOL] navigate_to_url STARTED - URL: {url}, link_text: {link_text}")
    
    
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
        # URL mapping done silently for performance
    
    # Validasi URL
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    
    # Generate link text if not provided
    if not link_text:
        # Extract page name from URL
        page_name = url.split('/')[-1] or url.split('/')[-2]
        link_text = f"Buka {page_name.replace('-', ' ').title()}"
    
    try:
        # Store URL in context for later widget streaming (after response completes)
        ctx.context.request_context['navigate_url_info'] = {
            'url': url,
            'link_text': link_text,
            'description': description
        }
        
        elapsed = time.time() - start_time
        print(f"✅ [TOOL] navigate_to_url completed in {elapsed:.2f}s")
        
        return {
            "url": url,
            "link_text": link_text,
            "description": description,
            "status": "success"
        }
    except Exception as exc:
        elapsed = time.time() - start_time
        print(f"❌ [TOOL] navigate_to_url failed in {elapsed:.2f}s - Error: {str(exc)}")
        return {
            "url": url,
            "status": "error",
            "error": str(exc)
        }


@function_tool(
    description_override="Generate images and visual content using AI. Use this when user explicitly asks to 'create', 'generate', 'make', or 'bikin' images, illustrations, logos, designs, or any visual content."
)
async def generate_image(
    ctx: RunContextWrapper[FactAgentContext],
    prompt: str,
    size: Literal["256x256", "512x512", "square", "portrait", "landscape"] | str = "512x512",
    partial_images: int = 1,
) -> dict[str, str | bool | None]:
    """Generate images using OpenAI's Responses API without streaming."""
    print("=" * 80)
    print("🎨 [IMAGE GENERATION TOOL] TOOL DIPANGGIL!")
    print(f"🎨 [IMAGE] Prompt: {prompt}")
    print(f"🎨 [IMAGE] Size: {size}")
    print(f"🎨 [IMAGE] Partial images: {partial_images}")
    print("=" * 80)
    logging.info(f"[IMAGE GENERATION] Tool called with prompt: {prompt[:100]}")
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("[IMAGE] ERROR: OPENAI_API_KEY not found")
        raise RuntimeError("Image generation requires OPENAI_API_KEY to be configured on the server.")
    
    client = OpenAI(api_key=api_key)

    try:
        print(f"🎨 [IMAGE] Using Responses API with model=gpt-5")
        
        # Use Responses API without streaming
        response = await asyncio.to_thread(
            client.responses.create,
            model="gpt-5",
            input=prompt,
            tools=[
                {
                    "type": "image_generation",
                    "background": "transparent",
                    "quality": "low",
                }
            ],
        )
        
        # Extract image data from output
        image_data = [
            output.result
            for output in response.output
            if output.type == "image_generation_call"
        ]
        
        if not image_data:
            print("[IMAGE] ERROR: No images received")
            raise RuntimeError("Image generation returned no images.")
        
        image_urls = []
        import io
        
        # Helper function untuk upload ke S3 di background
        async def upload_to_s3_async(image_bytes: bytes, idx: int) -> str | None:
            """Upload image to S3 asynchronously, return S3 URL or None if failed."""
            try:
                from .main import attachment_store
                attachment_id = attachment_store.generate_attachment_id("image/png", None)
                s3_key = attachment_store._get_s3_key(attachment_id)
                file_obj = io.BytesIO(image_bytes)
                
                # Upload S3 di thread terpisah agar tidak blocking
                upload_result = await asyncio.to_thread(
                    attachment_store.s3_client.upload_fileobj,
                    file_obj, s3_key, "image/png"
                )
                
                if upload_result["success"]:
                    s3_url = f"https://{attachment_store.s3_client.bucket_name}.s3.{attachment_store.s3_client.region}.amazonaws.com/{s3_key}"
                    print(f"🖼️ [IMAGE] Background upload #{idx} completed: {s3_url}")
                    return s3_url
                else:
                    print(f"🖼️ [IMAGE] Background upload #{idx} failed: {upload_result.get('error')}")
                    return None
            except Exception as e:
                print(f"🖼️ [IMAGE] Background upload #{idx} error: {e}")
                return None
        
        # Process images - stream widget dulu dengan data URL, upload S3 di background
        upload_tasks = []
        
        for idx, image_base64 in enumerate(image_data):
            try:
                # Convert to data URL untuk immediate display
                data_url = f"data:image/png;base64,{image_base64}"
                
                # Get image dimensions from base64 data
                try:
                    from PIL import Image as PILImage  # type: ignore[import-untyped]
                    import io
                    image_bytes = base64.b64decode(image_base64)
                    img = PILImage.open(io.BytesIO(image_bytes))
                    img_width, img_height = img.size
                    print(f"🖼️ [IMAGE] Image #{idx} dimensions: {img_width}x{img_height}")
                except ImportError:
                    print(f"🖼️ [IMAGE] PIL/Pillow not available, skipping dimension detection")
                    img_width, img_height = None, None
                except Exception as e:
                    print(f"🖼️ [IMAGE] Could not get dimensions for image #{idx}: {e}")
                    img_width, img_height = None, None
                
                # Stream widget immediately dengan data URL
                print(f"🖼️ [IMAGE] Creating widget for image #{idx} (data URL length: {len(data_url)})")
                widget_data = ImageGenerationWidgetData(
                    image_url=data_url,
                    prompt=prompt,
                    size=size,
                
                )
                print(f"🖼️ [IMAGE] Rendering widget for image #{idx}")
                widget = render_image_generation_widget(widget_data)
                copy_text = image_generation_widget_copy_text(widget_data)
                print(f"🖼️ [IMAGE] Streaming widget for image #{idx}...")
                try:
                    await ctx.context.stream_widget(widget, copy_text=copy_text)
                    print(f"✅ [IMAGE] Widget #{idx} streamed successfully!")
                except Exception as stream_error:
                    print(f"❌ [IMAGE] ERROR streaming widget #{idx}: {stream_error}")
                    import traceback
                    traceback.print_exc()
                    raise
                
                # Decode dan prepare upload ke S3 di background
                image_bytes = base64.b64decode(image_base64)
                upload_task = upload_to_s3_async(image_bytes, idx)
                upload_tasks.append((idx, upload_task))
                
            except Exception as e:
                print(f"🖼️ [IMAGE] Error processing image #{idx}: {e}")
                import traceback
                traceback.print_exc()
        
        # Start S3 uploads in background but don't wait - return immediately
        # This allows user to see images immediately while S3 uploads happen async
        if upload_tasks:
            print(f"🔄 [IMAGE] Starting {len(upload_tasks)} background S3 upload(s) (non-blocking)...")
            # Create background task to handle uploads without blocking response
            async def handle_uploads():
                for idx, task in upload_tasks:
                    try:
                        s3_url = await task
                        if s3_url:
                            print(f"✅ [IMAGE] Background upload #{idx} succeeded: {s3_url}")
                    except Exception as e:
                        print(f"❌ [IMAGE] Background upload #{idx} error: {e}")
            
            # Fire and forget - don't wait for completion
            asyncio.create_task(handle_uploads())
        
        # Return immediately with minimal info - images already visible via widget stream
        # Don't include data URLs in response to avoid exceeding max output size (1MB limit)
        return {
            "status": "generated",
            "prompt": prompt,
            "count": len(image_data),
            "message": f"Successfully generated {len(image_data)} image(s). Images have been displayed in the widget above. Upload to S3 is processing in the background."
        }
        
    except Exception as exc:
        print(f"[IMAGE] ERROR: {str(exc)}")
        raise RuntimeError(f"Image generation failed: {exc}") from exc


# Export all tools for easy importing
__all__ = [
    "save_fact",
    "switch_theme", 
    "get_weather",
    "match_cekat_docs_v1",
    "navigate_to_url",
    "create_prompt_tool",
    "generate_image",
    "FactAgentContext",
]
