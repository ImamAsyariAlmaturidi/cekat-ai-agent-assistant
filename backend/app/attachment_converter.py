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
        
        print(f"[DEBUG] Converting ThreadItem: {type(item).__name__}")
        print(f"[DEBUG] ThreadItem attributes: {dir(item)}")
        
        if isinstance(item, UserMessageItem):
            print(f"[DEBUG] Processing UserMessageItem with {len(item.content)} content parts")
            print(f"[DEBUG] UserMessageItem content: {item.content}")
            
            # Check if UserMessageItem has attachments attribute
            if hasattr(item, 'attachments') and item.attachments:
                print(f"[DEBUG] Found attachments in UserMessageItem: {len(item.attachments)}")
                for i, attachment in enumerate(item.attachments):
                    print(f"[DEBUG] Attachment {i}: {attachment.id}, type: {attachment.mime_type}")
            else:
                print(f"[DEBUG] No attachments attribute in UserMessageItem")
                print(f"[DEBUG] UserMessageItem has attachments attr: {hasattr(item, 'attachments')}")
                if hasattr(item, 'attachments'):
                    print(f"[DEBUG] UserMessageItem attachments value: {getattr(item, 'attachments', None)}")
            
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
                print(f"[DEBUG] Processing content part {i}: {type(part).__name__}")
                print(f"[DEBUG] Content part attributes: {dir(part)}")
                print(f"[DEBUG] Content part dict: {part.__dict__ if hasattr(part, '__dict__') else 'No __dict__'}")
                
                # Check for text content
                if hasattr(part, 'text') and part.text:
                    text_parts.append(part.text)
                    print(f"[DEBUG] Added text: {part.text[:50]}...")
                
                # Check for attachment content - try different attribute names
                attachment_obj = None
                if hasattr(part, 'attachment') and part.attachment:
                    attachment_obj = part.attachment
                    print(f"[DEBUG] Found attachment via 'attachment' attr: {attachment_obj.id}")
                elif hasattr(part, 'file') and part.file:
                    attachment_obj = part.file
                    print(f"[DEBUG] Found attachment via 'file' attr: {attachment_obj.id}")
                elif hasattr(part, 'image') and part.image:
                    attachment_obj = part.image
                    print(f"[DEBUG] Found attachment via 'image' attr: {attachment_obj.id}")
                elif hasattr(part, 'media') and part.media:
                    attachment_obj = part.media
                    print(f"[DEBUG] Found attachment via 'media' attr: {attachment_obj.id}")
                elif hasattr(part, 'data') and part.data:
                    attachment_obj = part.data
                    print(f"[DEBUG] Found attachment via 'data' attr: {attachment_obj.id}")
                elif hasattr(part, 'content') and part.content:
                    attachment_obj = part.content
                    print(f"[DEBUG] Found attachment via 'content' attr: {attachment_obj.id}")
                
                # Try to find attachment in any attribute
                if not attachment_obj:
                    for attr_name in ['attachment', 'file', 'image', 'media', 'data', 'content', 'url', 'src']:
                        if hasattr(part, attr_name):
                            attr_value = getattr(part, attr_name)
                            if attr_value and hasattr(attr_value, 'id'):
                                attachment_obj = attr_value
                                print(f"[DEBUG] Found attachment via '{attr_name}' attr: {attachment_obj.id}")
                                break
                
                if attachment_obj:
                    print(f"[DEBUG] Processing attachment: {attachment_obj.id}, type: {attachment_obj.mime_type}")
                    # Convert attachment to message content
                    try:
                        attachment_content = await self.attachment_to_message_content(attachment_obj)
                        attachment_contents.append(attachment_content)
                        print(f"[DEBUG] Successfully converted attachment {attachment_obj.id} to content")
                    except Exception as e:
                        print(f"[ERROR] Failed to convert attachment: {e}")
                        import traceback
                        traceback.print_exc()
                        # Add fallback text
                        text_parts.append(f"[Attachment: {attachment_obj.name or 'Unknown file'}]")
                else:
                    print(f"[DEBUG] No attachment found in content part")
                    print(f"[DEBUG] Part type: {type(part)}")
                    print(f"[DEBUG] Part has text attr: {hasattr(part, 'text')}")
                    print(f"[DEBUG] Part has attachment attr: {hasattr(part, 'attachment')}")
                    print(f"[DEBUG] Part has file attr: {hasattr(part, 'file')}")
                    print(f"[DEBUG] Part has image attr: {hasattr(part, 'image')}")
                    print(f"[DEBUG] Part has media attr: {hasattr(part, 'media')}")
                    print(f"[DEBUG] Part has data attr: {hasattr(part, 'data')}")
                    print(f"[DEBUG] Part has content attr: {hasattr(part, 'content')}")
                    print(f"[DEBUG] Part has url attr: {hasattr(part, 'url')}")
                    print(f"[DEBUG] Part has src attr: {hasattr(part, 'src')}")
                    
                    # Print all attribute values
                    for attr_name in dir(part):
                        if not attr_name.startswith('_'):
                            try:
                                attr_value = getattr(part, attr_name)
                                if not callable(attr_value):
                                    print(f"[DEBUG] {attr_name}: {attr_value}")
                            except:
                                pass
            
            print(f"[DEBUG] Final result - text_parts: {len(text_parts)}, attachment_contents: {len(attachment_contents)}")
            
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
                print(f"[DEBUG] Returning list with single message containing text and {len(attachment_contents)} attachments")
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
                print(f"[DEBUG] Returning list with single message containing {len(attachment_contents)} attachments only")
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
