"""FastAPI entrypoint wiring the ChatKit server and REST endpoints."""

from __future__ import annotations

from typing import Any
import os
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
async def direct_upload(file: UploadFile = File(...)) -> dict[str, Any]:
    """Direct upload endpoint for ChatKit attachments - handles multipart/form-data."""
    try:
        print(f"[DEBUG] Upload request received: {file.filename}, {file.content_type}")
        
        # Read file content
        content = await file.read()
        filename = file.filename or "unknown"
        content_type = file.content_type or "application/octet-stream"
        
        print(f"[DEBUG] File read: {len(content)} bytes, type: {content_type}")
        
        # Generate attachment ID using the store method
        attachment_id = attachment_store.generate_attachment_id(content_type, None)
        
        # Upload file to S3
        s3_key = attachment_store._get_s3_key(attachment_id)
        import io
        file_obj = io.BytesIO(content)
        upload_result = attachment_store.s3_client.upload_fileobj(
            file_obj, s3_key, content_type
        )
        
        if not upload_result["success"]:
            raise HTTPException(
                status_code=500,
                detail=f"S3 upload failed: {upload_result['error']}"
            )
        
        # Store metadata
        metadata = {
            "filename": filename,
            "content_type": content_type,
            "size": len(content),
            "status": "uploaded",
            "s3_key": s3_key
        }
        attachment_store.metadata_store[attachment_id] = metadata
        print(f"[DEBUG] Stored metadata for {attachment_id}: {metadata}")
        
        # Return FileAttachment or ImageAttachment format
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
        
        print(f"[DEBUG] Returning result: {result}")
        return result
        
    except Exception as e:
        print(f"[ERROR] Direct upload failed: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Direct upload failed: {str(e)}"
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

@app.post("/chatkit/files")
async def chatkit_direct_upload(request: Request) -> dict[str, Any]:
    """Direct upload endpoint for ChatKit attachments."""
    try:
        # Get file content
        body = await request.body()
        content_type = request.headers.get("content-type", "application/octet-stream")
        
        # Generate attachment ID from content
        attachment_id = attachment_store._generate_attachment_id("direct_upload", content_type)
        
        # Save file to disk
        file_path = attachment_store._get_file_path(attachment_id)
        with open(file_path, "wb") as f:
            f.write(body)
        
        # Store metadata
        metadata = {
            "filename": f"direct_upload_{attachment_id[:8]}",
            "content_type": content_type,
            "size": len(body),
            "status": "uploaded"
        }
        attachment_store.metadata_store[attachment_id] = metadata
        print(f"[DEBUG] Stored metadata for {attachment_id}: {metadata}")
        print(f"[DEBUG] Metadata store: {attachment_store.metadata_store}")
        
        return {
            "success": True,
            "message": "File uploaded successfully",
            "attachment_id": attachment_id,
            "size": len(body),
            "content_type": content_type
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Direct upload failed: {str(e)}"
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
        
        print(f"[DEBUG] Widget action received: {action}")
        print(f"[DEBUG] Item ID: {item_id}")
        
        action_type = action.get("type")
        payload = action.get("payload", {})
        
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