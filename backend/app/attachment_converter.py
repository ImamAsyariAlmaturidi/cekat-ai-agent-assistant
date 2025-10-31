"""Attachment handling utilities for ChatKit."""

import base64
from typing import Any
from chatkit.types import Attachment, ImageAttachment
from openai.types.responses import ResponseInputImageParam, ResponseInputFileParam


async def read_attachment_bytes(attachment_id: str) -> bytes:
    """Replace with your blob-store fetch (S3, local disk, etc.)."""
    from .main import attachment_store
    return await attachment_store.get_attachment_bytes(attachment_id)


class CustomThreadItemConverter:
    """Custom ThreadItemConverter untuk handle attachments dengan benar."""
    
    async def attachment_to_message_content(self, input: Attachment) -> ResponseInputImageParam | ResponseInputFileParam:
        """Convert attachment to message content sesuai dokumentasi ChatKit."""
        try:
            print(f"[ATTACHMENT_CONVERTER] Converting attachment {input.id}")
            print(f"[ATTACHMENT_CONVERTER] Input mime_type: {input.mime_type}")
            print(f"[ATTACHMENT_CONVERTER] Input name: {input.name}")
            
            # Get attachment bytes menggunakan helper function
            content = await read_attachment_bytes(input.id)
            print(f"[ATTACHMENT_CONVERTER] Read {len(content)} bytes from attachment")
            
            # Get correct mime_type from metadata store if available (to fix multipart/form-data issue)
            mime_type = input.mime_type
            from .main import attachment_store
            if hasattr(attachment_store, 'metadata_store') and input.id in attachment_store.metadata_store:
                metadata = attachment_store.metadata_store[input.id]
                stored_content_type = metadata.get('content_type') or metadata.get('mime_type')
                if stored_content_type and stored_content_type != 'multipart/form-data':
                    mime_type = stored_content_type
                    print(f"[ATTACHMENT_CONVERTER] Using mime_type from metadata: {mime_type}")
                else:
                    print(f"[ATTACHMENT_CONVERTER] Metadata mime_type also invalid: {stored_content_type}")
            
            # Validate mime_type - reject multipart/form-data
            if mime_type == 'multipart/form-data' or not mime_type or mime_type.startswith('multipart/'):
                # Try to detect from filename or content
                if input.name:
                    import mimetypes
                    detected_type, _ = mimetypes.guess_type(input.name)
                    if detected_type:
                        mime_type = detected_type
                        print(f"[ATTACHMENT_CONVERTER] Detected mime_type from filename: {mime_type}")
                    else:
                        # Default based on extension
                        if input.name.lower().endswith(('.jpg', '.jpeg')):
                            mime_type = 'image/jpeg'
                        elif input.name.lower().endswith('.png'):
                            mime_type = 'image/png'
                        elif input.name.lower().endswith('.pdf'):
                            mime_type = 'application/pdf'
                        else:
                            mime_type = 'application/octet-stream'
                        print(f"[ATTACHMENT_CONVERTER] Using default mime_type: {mime_type}")
                else:
                    # Try to detect from content (magic bytes)
                    if len(content) >= 4:
                        if content[:4] == b'\xff\xd8\xff\xe0' or content[:4] == b'\xff\xd8\xff\xe1':
                            mime_type = 'image/jpeg'
                        elif content[:8] == b'\x89PNG\r\n\x1a\n':
                            mime_type = 'image/png'
                        elif content[:4] == b'%PDF':
                            mime_type = 'application/pdf'
                        else:
                            mime_type = 'application/octet-stream'
                        print(f"[ATTACHMENT_CONVERTER] Detected mime_type from content: {mime_type}")
                    else:
                        mime_type = 'application/octet-stream'
                        print(f"[ATTACHMENT_CONVERTER] Using fallback mime_type: {mime_type}")
            
            print(f"[ATTACHMENT_CONVERTER] Final mime_type: {mime_type}")
            
            # Create data URL
            data = (
                "data:"
                + str(mime_type)
                + ";base64,"
                + base64.b64encode(content).decode("utf-8")
            )
            print(f"[ATTACHMENT_CONVERTER] Created data URL (length: {len(data)} chars)")
            
            # Return sesuai type attachment - check mime_type instead of isinstance for better detection
            # Treat as image if mime_type starts with image/ or if it's an ImageAttachment
            is_image = isinstance(input, ImageAttachment) or (mime_type and mime_type.startswith('image/'))
            
            if is_image:
                # For Agent SDK, we need to embed image in message content
                return {
                    "type": "message",
                    "role": "user", 
                    "content": [
                        {
                            "type": "input_image",
                            "image_url": data
                        }
                    ]
                }
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
    
    async def to_agent_input(self, item: Any, thread: Any) -> Any | None:
        """Convert ThreadItem to agent input, handling attachments properly."""
        from chatkit.types import UserMessageItem
        
        # Debug logging removed for performance
        
        if isinstance(item, UserMessageItem):
            # Debug logging removed for performance
            
            # Extract text content
            text_parts = []
            attachment_contents = []
            
            # Process attachments from UserMessageItem.attachments if they exist
            if hasattr(item, 'attachments') and item.attachments:
                print(f"[DEBUG] Processing {len(item.attachments)} attachments from UserMessageItem.attachments")
                for attachment in item.attachments:
                    try:
                        attachment_content = await self.attachment_to_message_content(attachment)
                        attachment_contents.append(attachment_content)
                        print(f"[DEBUG] Successfully converted attachment {attachment.id} to content")
                    except Exception as e:
                        print(f"[ERROR] Failed to convert attachment from UserMessageItem.attachments: {e}")
                        import traceback
                        traceback.print_exc()
                        # Add fallback text
                        text_parts.append(f"[Attachment: {attachment.name or 'Unknown file'}]")
            
            # TEMPORARY WORKAROUND: Check if there's a recent upload and attach it
            # This is a workaround for when ChatKit doesn't properly attach files
            if not attachment_contents and text_parts:
                # Check if the text mentions an image or if we can infer from context
                text_content = " ".join(text_parts).lower()
                if any(keyword in text_content for keyword in ['gambar', 'image', 'foto', 'photo', 'screenshot', 'ini apa']):
                    print(f"[DEBUG] Text suggests image content, checking for recent uploads...")
                    # Try to find the most recent upload
                    try:
                        from .main import attachment_store
                        if hasattr(attachment_store, 'metadata_store') and attachment_store.metadata_store:
                            # Get the most recent upload
                            recent_uploads = list(attachment_store.metadata_store.items())
                            if recent_uploads:
                                # Sort by some criteria (this is a simple workaround)
                                latest_id, latest_metadata = recent_uploads[-1]
                                if latest_metadata.get('content_type', '').startswith('image/'):
                                    print(f"[DEBUG] Found recent image upload: {latest_id}")
                                    # Create a mock attachment object
                                    from chatkit.types import ImageAttachment
                                    mock_attachment = ImageAttachment(
                                        id=latest_id,
                                        name=latest_metadata.get('filename', 'image'),
                                        mime_type=latest_metadata.get('content_type', 'image/png'),
                                        size=latest_metadata.get('size', 0)
                                    )
                                    try:
                                        attachment_content = await self.attachment_to_message_content(mock_attachment)
                                        attachment_contents.append(attachment_content)
                                        print(f"[DEBUG] Successfully attached recent upload {latest_id}")
                                    except Exception as e:
                                        print(f"[ERROR] Failed to attach recent upload: {e}")
                    except Exception as e:
                        print(f"[ERROR] Failed to check recent uploads: {e}")
            
            # Process each content part
            for i, part in enumerate(item.content):
                # Debug logging removed for performance
                
                # Check for text content
                if hasattr(part, 'text') and part.text:
                    text_parts.append(part.text)
                
                # Check for attachment content - debug logging removed for performance
                attachment_obj = None
                if hasattr(part, 'attachment') and part.attachment:
                    attachment_obj = part.attachment
                elif hasattr(part, 'file') and part.file:
                    attachment_obj = part.file
                elif hasattr(part, 'image') and part.image:
                    attachment_obj = part.image
                elif hasattr(part, 'media') and part.media:
                    attachment_obj = part.media
                elif hasattr(part, 'data') and part.data:
                    attachment_obj = part.data
                elif hasattr(part, 'content') and part.content:
                    attachment_obj = part.content
                
                # Try to find attachment in any attribute
                if not attachment_obj:
                    for attr_name in ['attachment', 'file', 'image', 'media', 'data', 'content', 'url', 'src']:
                        if hasattr(part, attr_name):
                            attr_value = getattr(part, attr_name)
                            if attr_value and hasattr(attr_value, 'id'):
                                attachment_obj = attr_value
                                break
                
                if attachment_obj:
                    # Convert attachment to message content
                    try:
                        attachment_content = await self.attachment_to_message_content(attachment_obj)
                        attachment_contents.append(attachment_content)
                    except Exception as e:
                        print(f"[ERROR] Failed to convert attachment: {e}")
                        # Add fallback text
                        text_parts.append(f"[Attachment: {attachment_obj.name or 'Unknown file'}]")
            
            # Combine text and attachments - return proper format for Agent SDK
            if text_parts and attachment_contents:
                # Return single message with both text and image content
                content = []
                content.append({"type": "input_text", "text": " ".join(text_parts).strip()})
                for attachment in attachment_contents:
                    if isinstance(attachment, dict) and attachment.get("type") == "message":
                        # Extract image content from attachment message
                        content.extend(attachment["content"])
                    else:
                        content.append(attachment)
                
                result = [{
                    "type": "message",
                    "role": "user",
                    "content": content
                }]
                return result
            elif attachment_contents:
                # Only attachments, no text
                content = []
                for attachment in attachment_contents:
                    if isinstance(attachment, dict) and attachment.get("type") == "message":
                        content.extend(attachment["content"])
                    else:
                        content.append(attachment)
                
                result = [{
                    "type": "message", 
                    "role": "user",
                    "content": content
                }]
                return result
            elif text_parts:
                # Only text, no attachments
                result = " ".join(text_parts).strip()
                return result
            else:
                # Empty message
                return ""
        
        # For other types, return None to use default handling
        return None
