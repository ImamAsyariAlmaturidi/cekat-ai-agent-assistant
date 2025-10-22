from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List

from chatkit.store import NotFoundError, Store
from chatkit.types import Attachment, Page, Thread, ThreadItem, ThreadMetadata


@dataclass
class _ThreadState:
    thread: ThreadMetadata
    items: List[ThreadItem]


class MemoryStore(Store[dict[str, Any]]):
    """Simple in-memory store compatible with the ChatKit server interface."""

    def __init__(self) -> None:
        self._threads: Dict[str, _ThreadState] = {}
        # Attachments intentionally unsupported; use a real store that enforces auth.

    @staticmethod
    def _coerce_thread_metadata(thread: ThreadMetadata | Thread) -> ThreadMetadata:
        """Return thread metadata without any embedded items (openai-chatkit>=1.0)."""
        has_items = isinstance(thread, Thread) or "items" in getattr(
            thread, "model_fields_set", set()
        )
        if not has_items:
            return thread.model_copy(deep=True)

        data = thread.model_dump()
        data.pop("items", None)
        return ThreadMetadata(**data).model_copy(deep=True)

    # -- Thread metadata -------------------------------------------------
    async def load_thread(self, thread_id: str, context: dict[str, Any]) -> ThreadMetadata:
        state = self._threads.get(thread_id)
        if not state:
            raise NotFoundError(f"Thread {thread_id} not found")
        return self._coerce_thread_metadata(state.thread)

    async def save_thread(self, thread: ThreadMetadata, context: dict[str, Any]) -> None:
        metadata = self._coerce_thread_metadata(thread)
        state = self._threads.get(thread.id)
        if state:
            state.thread = metadata
        else:
            self._threads[thread.id] = _ThreadState(
                thread=metadata,
                items=[],
            )

    async def load_threads(
        self,
        limit: int,
        after: str | None,
        order: str,
        context: dict[str, Any],
    ) -> Page[ThreadMetadata]:
        threads = sorted(
            (self._coerce_thread_metadata(state.thread) for state in self._threads.values()),
            key=lambda t: t.created_at or datetime.min,
            reverse=(order == "desc"),
        )

        if after:
            index_map = {thread.id: idx for idx, thread in enumerate(threads)}
            start = index_map.get(after, -1) + 1
        else:
            start = 0

        slice_threads = threads[start : start + limit + 1]
        has_more = len(slice_threads) > limit
        slice_threads = slice_threads[:limit]
        next_after = slice_threads[-1].id if has_more and slice_threads else None
        return Page(
            data=slice_threads,
            has_more=has_more,
            after=next_after,
        )

    async def delete_thread(self, thread_id: str, context: dict[str, Any]) -> None:
        self._threads.pop(thread_id, None)

    # -- Thread items ----------------------------------------------------
    def _items(self, thread_id: str) -> List[ThreadItem]:
        state = self._threads.get(thread_id)
        if state is None:
            state = _ThreadState(
                thread=ThreadMetadata(id=thread_id, created_at=datetime.utcnow()),
                items=[],
            )
            self._threads[thread_id] = state
        return state.items

    async def load_thread_items(
        self,
        thread_id: str,
        after: str | None,
        limit: int,
        order: str,
        context: dict[str, Any],
    ) -> Page[ThreadItem]:
        items = [item.model_copy(deep=True) for item in self._items(thread_id)]
        items.sort(
            key=lambda item: getattr(item, "created_at", datetime.utcnow()),
            reverse=(order == "desc"),
        )

        if after:
            index_map = {item.id: idx for idx, item in enumerate(items)}
            start = index_map.get(after, -1) + 1
        else:
            start = 0

        slice_items = items[start : start + limit + 1]
        has_more = len(slice_items) > limit
        slice_items = slice_items[:limit]
        next_after = slice_items[-1].id if has_more and slice_items else None
        return Page(data=slice_items, has_more=has_more, after=next_after)

    async def add_thread_item(
        self, thread_id: str, item: ThreadItem, context: dict[str, Any]
    ) -> None:
        self._items(thread_id).append(item.model_copy(deep=True))

    async def save_item(self, thread_id: str, item: ThreadItem, context: dict[str, Any]) -> None:
        items = self._items(thread_id)
        for idx, existing in enumerate(items):
            if existing.id == item.id:
                items[idx] = item.model_copy(deep=True)
                return
        items.append(item.model_copy(deep=True))

    async def load_item(self, thread_id: str, item_id: str, context: dict[str, Any]) -> ThreadItem:
        for item in self._items(thread_id):
            if item.id == item_id:
                return item.model_copy(deep=True)
        raise NotFoundError(f"Item {item_id} not found")

    async def delete_thread_item(
        self, thread_id: str, item_id: str, context: dict[str, Any]
    ) -> None:
        items = self._items(thread_id)
        self._threads[thread_id].items = [item for item in items if item.id != item_id]

    # -- Files -----------------------------------------------------------
    # These methods are not currently used but required to be compatible with the Store interface.

    async def save_attachment(
        self,
        attachment: Attachment,
        context: dict[str, Any],
    ) -> None:
        """Save attachment metadata to the attachment store."""
        # Import here to avoid circular imports
        from .main import attachment_store
        
        # Store attachment metadata
        attachment_store.metadata_store[attachment.id] = {
            "filename": attachment.name,
            "content_type": attachment.mime_type,
            "size": getattr(attachment, 'size', 0),
            "status": "saved",
            "attachment": attachment
        }

    async def load_attachment(
        self,
        attachment_id: str,
        context: dict[str, Any],
    ) -> Attachment:
        """Load attachment from the attachment store."""
        # Import here to avoid circular imports
        from .main import attachment_store
        
        if attachment_id not in attachment_store.metadata_store:
            raise ValueError(f"Attachment {attachment_id} not found")
        
        metadata = attachment_store.metadata_store[attachment_id]
        
        # Return the stored attachment object
        if "attachment" in metadata:
            return metadata["attachment"]
        
        # Fallback: create attachment from metadata
        from chatkit.types import FileAttachment, ImageAttachment
        
        if metadata["content_type"].startswith("image/"):
            return ImageAttachment(
                id=attachment_id,
                name=metadata["filename"],
                mime_type=metadata["content_type"],
                url=f"http://localhost:8000/chatkit/files/{attachment_id}/download",
                preview_url=f"http://localhost:8000/chatkit/files/{attachment_id}/download"
            )
        else:
            return FileAttachment(
                id=attachment_id,
                name=metadata["filename"],
                mime_type=metadata["content_type"]
            )

    async def delete_attachment(self, attachment_id: str, context: dict[str, Any]) -> None:
        """Delete attachment from the attachment store."""
        # Import here to avoid circular imports
        from .main import attachment_store
        
        if attachment_id in attachment_store.metadata_store:
            del attachment_store.metadata_store[attachment_id]
