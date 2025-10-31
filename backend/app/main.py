"""FastAPI entrypoint wiring the ChatKit server and REST endpoints."""

from __future__ import annotations

from typing import Any
import os

# Disable OpenAI tracing for performance - MUST be before any imports
os.environ['OPENAI_TRACING_DISABLED'] = 'true'
os.environ['OTEL_SDK_DISABLED'] = 'true'
import uuid
import hashlib
from pathlib import Path
from typing import Dict, Any
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from chatkit.server import StreamingResult, ChatKitServer
from chatkit.store import AttachmentStore, AttachmentCreateParams
from chatkit.types import FileAttachment, ImageAttachment, Attachment
from fastapi import Depends, FastAPI, HTTPException, Request, status, UploadFile, File
from fastapi.responses import Response, StreamingResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from urllib.parse import unquote

from .server import (
    FactAssistantServer,
    create_chatkit_server,
)
from .facts import fact_store
from .s3_client import get_cekat_s3_client

class S3AttachmentStore(AttachmentStore):
    """S3 file storage implementation for ChatKit attachments."""
    
    def __init__(self):
        self.s3_client = get_cekat_s3_client()
        # Simple in-memory metadata store (in production, use a database)
        self.metadata_store: Dict[str, Dict[str, Any]] = {}
    
    def generate_attachment_id(self, mime_type: str, context: Any) -> str:
        """Generate unique attachment ID."""
        unique_string = f"{mime_type}_{uuid.uuid4()}"
        return hashlib.md5(unique_string.encode()).hexdigest()
    
    def _get_s3_key(self, attachment_id: str) -> str:
        """Get S3 key for attachment ID."""
        return f"attachments/{attachment_id}"
    
    async def create_attachment(self, input: AttachmentCreateParams, context: Any) -> Attachment:
        """Create attachment metadata and return upload URL."""
        try:
            # Generate attachment ID
            attachment_id = self.generate_attachment_id(input.mime_type, context)
            s3_key = self._get_s3_key(attachment_id)
            
            # Create attachment object based on type
            if input.mime_type.startswith("image/"):
                attachment = ImageAttachment(
                    id=attachment_id,
                    name=input.name or "image",
                    mime_type=input.mime_type,
                    size=input.size,
                    url=f"https://{self.s3_client.bucket_name}.s3.{self.s3_client.region}.amazonaws.com/{s3_key}",
                    preview_url=f"https://{self.s3_client.bucket_name}.s3.{self.s3_client.region}.amazonaws.com/{s3_key}"
                )
            else:
                attachment = FileAttachment(
                    id=attachment_id,
                    name=input.name or "file",
                    mime_type=input.mime_type,
                    size=input.size
                )
            
            # Store metadata
            self.metadata_store[attachment_id] = {
                "filename": input.name or "unknown",
                "content_type": input.mime_type,
                "size": input.size,
                "status": "pending",
                "attachment": attachment,
                "s3_key": s3_key
            }
            
            # Set upload URL for two-phase upload
            attachment.upload_url = f"http://localhost:8000/chatkit/files/{attachment_id}"
            
            return attachment
            
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create attachment: {str(e)}"
            )
    
    async def delete_attachment(self, attachment_id: str, context: Any) -> None:
        """Delete attachment and its metadata."""
        try:
            if attachment_id not in self.metadata_store:
                raise HTTPException(
                    status_code=404,
                    detail="Attachment not found"
                )
            
            # Delete file from S3
            metadata = self.metadata_store[attachment_id]
            s3_key = metadata.get("s3_key")
            if s3_key:
                result = self.s3_client.delete_file(s3_key)
                if not result["success"]:
                    print(f"Warning: Failed to delete S3 file {s3_key}: {result['error']}")
            
            # Remove metadata
            del self.metadata_store[attachment_id]
            
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to delete attachment: {str(e)}"
            )
    
    async def get_attachment_bytes(self, attachment_id: str) -> bytes:
        """Get attachment file bytes for Agent SDK integration."""
        try:
            if attachment_id not in self.metadata_store:
                raise HTTPException(
                    status_code=404,
                    detail="Attachment not found"
                )
            
            metadata = self.metadata_store[attachment_id]
            s3_key = metadata.get("s3_key")
            if not s3_key:
                raise HTTPException(
                    status_code=404,
                    detail="S3 key not found for attachment"
                )
            
            # Download file from S3 to temporary location
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                result = self.s3_client.download_file(s3_key, temp_file.name)
                if not result["success"]:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Failed to download from S3: {result['error']}"
                    )
                
                # Read the downloaded file
                with open(temp_file.name, "rb") as f:
                    content = f.read()
                
                # Clean up temp file
                import os
                os.unlink(temp_file.name)
                
                return content
                
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to read attachment bytes: {str(e)}"
            )

app = FastAPI(title="ChatKit API")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global request logger middleware
@app.middleware("http")
async def log_all_requests(request: Request, call_next):
    try:
        client_ip = getattr(request.client, "host", None)
        print(f"[HTTP][REQ] {request.method} {request.url} ip={client_ip}")
        # Log headers as a plain dict (can be large)
        try:
            headers_dict = {k: v for k, v in request.headers.items()}
            print(f"[HTTP][HEADERS] {headers_dict}")
        except Exception as e:
            print(f"[HTTP][HEADERS][ERROR] {str(e)}")
    except Exception as e:
        print(f"[HTTP][REQ][ERROR] Failed to log request: {str(e)}")

    response = await call_next(request)

    try:
        print(f"[HTTP][RES] {request.method} {request.url.path} -> {response.status_code}")
    except Exception as e:
        print(f"[HTTP][RES][ERROR] {str(e)}")

    return response

# Initialize attachment store as global singleton
attachment_store = S3AttachmentStore()

_chatkit_server: FactAssistantServer | None = create_chatkit_server(attachment_store)


def get_chatkit_server() -> FactAssistantServer:
    if _chatkit_server is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "ChatKit dependencies are missing. Install the ChatKit Python "
                "package to enable the conversational endpoint."
            ),
        )
    return _chatkit_server


@app.post("/chatkit")
async def chatkit_endpoint(
    request: Request, server: FactAssistantServer = Depends(get_chatkit_server)
) -> Response:
    # Log inbound request with dynamic URL info (from ChatKit-Domain-Key header)
    try:
        domain_key = request.headers.get("chatkit-domain-key", "")
        parsed_url = None
        if "|url=" in domain_key:
            parsed_url = unquote(domain_key.split("|url=", 1)[1])
        client_ip = getattr(request.client, "host", None)
        print(
            f"[CHATKIT][REQ] {request.method} {request.url.path} ip={client_ip} url={parsed_url} domain_key={domain_key}"
        )
    except Exception as e:
        print(f"[CHATKIT][REQ][ERROR] Failed to log request: {str(e)}")

    payload = await request.body()
    result = await server.process(payload, {"request": request})
    if isinstance(result, StreamingResult):
        return StreamingResponse(result, media_type="text/event-stream")
    if hasattr(result, "json"):
        return Response(content=result.json, media_type="application/json")
    return JSONResponse(result)


@app.get("/facts")
async def list_facts() -> dict[str, Any]:
    facts = await fact_store.list_saved()
    return {"facts": [fact.as_dict() for fact in facts]}


@app.post("/facts/{fact_id}/save")
async def save_fact(fact_id: str) -> dict[str, Any]:
    fact = await fact_store.mark_saved(fact_id)
    if fact is None:
        raise HTTPException(status_code=404, detail="Fact not found")
    return {"fact": fact.as_dict()}


@app.post("/facts/{fact_id}/discard")
async def discard_fact(fact_id: str) -> dict[str, Any]:
    fact = await fact_store.discard(fact_id)
    if fact is None:
        raise HTTPException(status_code=404, detail="Fact not found")
    return {"fact": fact.as_dict()}

@app.post("/chatkit/files")
async def chatkit_files_upload(request: Request) -> dict[str, Any]:
    """Flexible upload endpoint for ChatKit attachments - handles both multipart/form-data and raw body."""
    try:
        # ===== DETAILED REQUEST LOGGING =====
        print("=" * 80)
        print("[CHATKIT][FILES] ========== NEW UPLOAD REQUEST ==========")
        
        # Log request basics
        client_ip = getattr(request.client, "host", None)
        method = request.method
        url_path = request.url.path
        query_params = dict(request.query_params)
        
        print(f"[CHATKIT][FILES][REQ] Method: {method}")
        print(f"[CHATKIT][FILES][REQ] Path: {url_path}")
        print(f"[CHATKIT][FILES][REQ] Query params: {query_params}")
        print(f"[CHATKIT][FILES][REQ] Client IP: {client_ip}")
        
        # Log all headers
        print("[CHATKIT][FILES][REQ] Headers:")
        for header_name, header_value in request.headers.items():
            if header_name.lower() in ["content-type", "content-length", "chatkit-domain-key"]:
                print(f"  {header_name}: {header_value}")
            else:
                print(f"  {header_name}: {header_value[:100]}..." if len(str(header_value)) > 100 else f"  {header_name}: {header_value}")
        
        # Extract ChatKit domain info
        domain_key = request.headers.get("chatkit-domain-key", "")
        parsed_url = None
        if "|url=" in domain_key:
            parsed_url = unquote(domain_key.split("|url=", 1)[1])
            print(f"[CHATKIT][FILES][REQ] Parsed URL: {parsed_url}")
        
        # Get content type
        content_type_header = request.headers.get("content-type", "")
        content_length = request.headers.get("content-length", "unknown")
        print(f"[CHATKIT][FILES][REQ] Content-Type: {content_type_header}")
        print(f"[CHATKIT][FILES][REQ] Content-Length: {content_length}")
        
        # ===== PROCESS REQUEST BASED ON CONTENT TYPE =====
        content: bytes
        filename: str = "unknown"
        content_type: str = "application/octet-stream"
        
        if "multipart/form-data" in content_type_header:
            print("[CHATKIT][FILES][REQ] Detected multipart/form-data")
            
            # Extract boundary from content-type
            boundary = None
            if "boundary=" in content_type_header:
                boundary = content_type_header.split("boundary=")[1].strip('"\'')
                print(f"[CHATKIT][FILES][REQ] Boundary: {boundary}")
            
            try:
                print("[CHATKIT][FILES][REQ] Attempting to parse multipart form...")
                form = await request.form()
                print(f"[CHATKIT][FILES][REQ] Form parsed successfully. Fields: {list(form.keys())}")
                
                # Try to find file in form
                file_obj = None
                file_field_name = None
                
                # Check common field names first
                for field_name in ["file", "attachment", "upload", "data"]:
                    if field_name in form:
                        value = form[field_name]
                        print(f"[CHATKIT][FILES][REQ] Found field '{field_name}': type={type(value)}")
                        if isinstance(value, UploadFile):
                            file_obj = value
                            file_field_name = field_name
                            print(f"[CHATKIT][FILES][REQ] Field '{field_name}' is an UploadFile!")
                            break
                
                # If not found, iterate through all fields
                if file_obj is None:
                    print("[CHATKIT][FILES][REQ] Searching through all form fields...")
                    for key, value in form.items():
                        print(f"[CHATKIT][FILES][REQ] Field '{key}': type={type(value)}, value={str(value)[:50] if not isinstance(value, UploadFile) else 'UploadFile'}")
                        if isinstance(value, UploadFile):
                            file_obj = value
                            file_field_name = key
                            print(f"[CHATKIT][FILES][REQ] Found UploadFile in field '{key}'!")
                            break
                
                if file_obj is not None:
                    print(f"[CHATKIT][FILES][REQ] Reading file from field '{file_field_name}'...")
                    content = await file_obj.read()
                    filename = file_obj.filename or "unknown"
                    content_type = file_obj.content_type or "application/octet-stream"
                    print(f"[CHATKIT][FILES][REQ] File read: {len(content)} bytes")
                    print(f"[CHATKIT][FILES][REQ] Filename: {filename}")
                    print(f"[CHATKIT][FILES][REQ] Content-Type: {content_type}")
                else:
                    error_msg = f"No file found in multipart form. Available fields: {list(form.keys())}"
                    print(f"[CHATKIT][FILES][ERROR] {error_msg}")
                    raise HTTPException(
                        status_code=400,
                        detail=error_msg
                    )
                    
            except HTTPException:
                raise
            except Exception as e:
                error_msg = str(e)
                error_type = type(e).__name__
                print(f"[CHATKIT][FILES][ERROR] Failed to parse multipart form!")
                print(f"[CHATKIT][FILES][ERROR] Error type: {error_type}")
                print(f"[CHATKIT][FILES][ERROR] Error message: {error_msg}")
                import traceback
                print("[CHATKIT][FILES][ERROR] Full traceback:")
                traceback.print_exc()
                
                # Try to read raw body as fallback
                print("[CHATKIT][FILES][REQ] Attempting fallback to raw body parsing...")
                try:
                    # Note: This might fail if body was already consumed
                    content = await request.body()
                    content_type = request.headers.get("content-type", "application/octet-stream")
                    filename = f"fallback_upload_{len(content)}"
                    print(f"[CHATKIT][FILES][REQ] Fallback successful: {len(content)} bytes")
                except Exception as read_error:
                    print(f"[CHATKIT][FILES][ERROR] Fallback also failed: {str(read_error)}")
                    raise HTTPException(
                        status_code=400,
                        detail=f"Failed to parse multipart form: {error_msg}. Fallback also failed: {str(read_error)}"
                    )
        else:
            # Handle raw body upload
            print("[CHATKIT][FILES][REQ] Detected raw body upload")
            try:
                content = await request.body()
                content_type = request.headers.get("content-type", "application/octet-stream")
                print(f"[CHATKIT][FILES][REQ] Raw body read: {len(content)} bytes")
                
                # Try to extract filename from content-disposition
                content_disposition = request.headers.get("content-disposition", "")
                if "filename=" in content_disposition:
                    try:
                        filename = content_disposition.split("filename=")[1].strip('"\'')
                        print(f"[CHATKIT][FILES][REQ] Filename from header: {filename}")
                    except:
                        filename = f"direct_upload_{len(content)}"
                        print(f"[CHATKIT][FILES][REQ] Using generated filename: {filename}")
                else:
                    filename = f"direct_upload_{len(content)}"
                    print(f"[CHATKIT][FILES][REQ] Using generated filename: {filename}")
            except Exception as e:
                print(f"[CHATKIT][FILES][ERROR] Failed to read raw body: {str(e)}")
                import traceback
                traceback.print_exc()
                raise HTTPException(
                    status_code=400,
                    detail=f"Failed to read request body: {str(e)}"
                )
        
        # ===== VALIDATE CONTENT =====
        if len(content) == 0:
            print("[CHATKIT][FILES][ERROR] Empty file content!")
            raise HTTPException(
                status_code=400,
                detail="Empty file content"
            )
        
        print(f"[CHATKIT][FILES][REQ] Final file info:")
        print(f"  - Size: {len(content)} bytes")
        print(f"  - Filename: {filename}")
        print(f"  - Content-Type: {content_type}")
        
        # ===== UPLOAD TO S3 =====
        print("[CHATKIT][FILES][REQ] Generating attachment ID...")
        attachment_id = attachment_store.generate_attachment_id(content_type, None)
        print(f"[CHATKIT][FILES][REQ] Attachment ID: {attachment_id}")
        
        print("[CHATKIT][FILES][REQ] Uploading to S3...")
        s3_key = attachment_store._get_s3_key(attachment_id)
        import io
        file_obj = io.BytesIO(content)
        upload_result = attachment_store.s3_client.upload_fileobj(
            file_obj, s3_key, content_type
        )
        
        if not upload_result["success"]:
            print(f"[CHATKIT][FILES][ERROR] S3 upload failed: {upload_result.get('error')}")
            raise HTTPException(
                status_code=500,
                detail=f"S3 upload failed: {upload_result.get('error', 'Unknown error')}"
            )
        
        print(f"[CHATKIT][FILES][REQ] S3 upload successful. URL: {upload_result.get('url')}")
        
        # ===== STORE METADATA =====
        metadata = {
            "filename": filename,
            "content_type": content_type,
            "size": len(content),
            "status": "uploaded",
            "s3_key": s3_key
        }
        attachment_store.metadata_store[attachment_id] = metadata
        print(f"[CHATKIT][FILES][REQ] Metadata stored: {metadata}")
        
        # ===== PREPARE RESPONSE =====
        if content_type.startswith("image/"):
            result = {
                "id": attachment_id,
                "type": "image",
                "url": upload_result["url"],
                "preview_url": upload_result["url"],
                "name": filename,
                "mime_type": content_type,
                "size": len(content)
            }
        else:
            result = {
                "id": attachment_id,
                "type": "file",
                "url": upload_result["url"],
                "name": filename,
                "mime_type": content_type,
                "size": len(content)
            }
        
        print(f"[CHATKIT][FILES][REQ] Returning result: {result}")
        print("=" * 80)
        return result
        
    except HTTPException:
        print("[CHATKIT][FILES][ERROR] HTTPException raised")
        print("=" * 80)
        raise
    except Exception as e:
        error_type = type(e).__name__
        error_msg = str(e)
        print(f"[CHATKIT][FILES][ERROR] Unexpected error!")
        print(f"[CHATKIT][FILES][ERROR] Error type: {error_type}")
        print(f"[CHATKIT][FILES][ERROR] Error message: {error_msg}")
        import traceback
        print("[CHATKIT][FILES][ERROR] Full traceback:")
        traceback.print_exc()
        print("=" * 80)
        raise HTTPException(
            status_code=500,
            detail=f"Direct upload failed: {error_msg}"
        )

@app.post("/attachments/create")
async def create_attachment(request: Request) -> dict[str, Any]:
    """Two-phase upload Phase 1: Create attachment metadata."""
    try:
        data = await request.json()
        
        # Create AttachmentCreateParams
        create_params = AttachmentCreateParams(
            name=data.get("name", "unknown"),
            mime_type=data.get("mime_type", "application/octet-stream"),
            size=data.get("size", 0)
        )
        
        # Create attachment using store
        attachment = await attachment_store.create_attachment(create_params, None)
        
        return {
            "id": attachment.id,
            "type": "image" if attachment.mime_type.startswith("image/") else "file",
            "url": getattr(attachment, 'url', f"/chatkit/files/{attachment.id}/download"),
            "preview_url": getattr(attachment, 'preview_url', None),
            "name": attachment.name,
            "mime_type": attachment.mime_type,
            "size": create_params.size,
            "upload_url": attachment.upload_url
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create attachment: {str(e)}"
        )


@app.post("/chatkit/files/{attachment_id}")
async def upload_file(attachment_id: str, file: UploadFile = File(...)) -> dict[str, Any]:
    """Two-phase upload Phase 2: Upload file bytes to attachment."""
    try:
        # Read file content
        content = await file.read()
        filename = file.filename or "unknown"
        content_type = file.content_type or "application/octet-stream"
        
        # Save file to disk
        file_path = attachment_store._get_file_path(attachment_id)
        with open(file_path, "wb") as f:
            f.write(content)
        
        # Update metadata
        if attachment_id in attachment_store.metadata_store:
            metadata = attachment_store.metadata_store[attachment_id]
            metadata["status"] = "uploaded"
            metadata["actual_size"] = len(content)
            metadata["filename"] = filename
            metadata["content_type"] = content_type
            
            # Update attachment object if it exists
            if "attachment" in metadata:
                attachment = metadata["attachment"]
                # Note: FileAttachment and ImageAttachment don't have mutable size field
                # We'll just update the metadata store
                pass
        
        return {
            "success": True,
            "message": "File uploaded successfully",
            "attachment_id": attachment_id,
            "size": len(content),
            "content_type": content_type
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"File upload failed: {str(e)}"
        )

@app.get("/chatkit/files/{attachment_id}/download")
async def download_file(attachment_id: str) -> Response:
    """Download uploaded file from S3 using presigned URL for better performance."""
    try:
        if attachment_id not in attachment_store.metadata_store:
            raise HTTPException(status_code=404, detail="Attachment not found")
        
        metadata = attachment_store.metadata_store[attachment_id]
        s3_key = metadata.get("s3_key")
        
        if not s3_key:
            raise HTTPException(status_code=404, detail="S3 key not found for attachment")
        
        # Generate presigned URL for direct S3 access (much faster)
        presigned_result = attachment_store.s3_client.generate_presigned_url(s3_key, expiration=3600)
        
        if not presigned_result["success"]:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to generate presigned URL: {presigned_result['error']}"
            )
        
        # Redirect to presigned URL for direct S3 access
        from fastapi.responses import RedirectResponse
        return RedirectResponse(
            url=presigned_result["url"],
            status_code=302,
            headers={
                "Content-Disposition": f"attachment; filename={metadata['filename']}"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Download failed: {str(e)}"
        )

@app.post("/api/widget-action")
async def handle_widget_action(request: Request) -> dict[str, Any]:
    """Handle widget actions from ChatKit frontend."""
    try:
        data = await request.json()
        action = data.get("action", {})
        item_id = data.get("itemId")
        
        print(f"🔵 [WIDGET] Widget action received: {action}")
        print(f"🔵 [WIDGET] Item ID: {item_id}")
        
        action_type = action.get("type")
        payload = action.get("payload", {})
        
        print(f"🔍 [WIDGET] Action type: {action_type}")
        print(f"🔍 [WIDGET] Payload: {payload}")
        
        if action_type == "navigation.open":
            url = payload.get("url")
            if url:
                print(f"[DEBUG] Navigation action: Opening URL {url}")
                # For now, just log the action
                # In the future, we could add more sophisticated handling here
                return {
                    "success": True,
                    "message": f"Navigation to {url} handled",
                    "action_type": action_type,
                    "url": url
                }
        
        return {
            "success": True,
            "message": f"Action {action_type} handled",
            "action_type": action_type
        }
        
    except Exception as e:
        print(f"[ERROR] Widget action failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Widget action failed: {str(e)}"
        )

@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "healthy"}