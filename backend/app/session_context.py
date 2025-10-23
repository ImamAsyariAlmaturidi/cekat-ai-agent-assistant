"""Session context management untuk ChatKit server."""

import json
import asyncio
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from pathlib import Path

@dataclass
class ConversationTurn:
    """Single turn dalam percakapan."""
    timestamp: str
    role: str  # 'user' atau 'assistant'
    content: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    metadata: Optional[Dict[str, Any]] = None

@dataclass
class SessionContext:
    """Context untuk satu session percakapan."""
    session_id: str
    created_at: str
    last_updated: str
    conversation_history: List[ConversationTurn]
    user_preferences: Dict[str, Any]
    session_metadata: Dict[str, Any]
    
    def add_turn(self, role: str, content: str, tool_calls: Optional[List[Dict[str, Any]]] = None, metadata: Optional[Dict[str, Any]] = None):
        """Tambahkan turn baru ke conversation history."""
        turn = ConversationTurn(
            timestamp=datetime.now().isoformat(),
            role=role,
            content=content,
            tool_calls=tool_calls,
            metadata=metadata
        )
        self.conversation_history.append(turn)
        self.last_updated = datetime.now().isoformat()
    
    def get_recent_context(self, max_turns: int = 10) -> str:
        """Ambil context dari percakapan terakhir."""
        recent_turns = self.conversation_history[-max_turns:] if len(self.conversation_history) > max_turns else self.conversation_history
        
        context_parts = []
        for turn in recent_turns:
            if turn.role == 'user':
                context_parts.append(f"User: {turn.content}")
            elif turn.role == 'assistant':
                context_parts.append(f"Assistant: {turn.content}")
                if turn.tool_calls:
                    for tool_call in turn.tool_calls:
                        context_parts.append(f"  [Tool: {tool_call.get('name', 'unknown')}]")
        
        return "\n".join(context_parts)
    
    def get_summary(self) -> str:
        """Buat summary dari session."""
        total_turns = len(self.conversation_history)
        user_turns = len([t for t in self.conversation_history if t.role == 'user'])
        assistant_turns = len([t for t in self.conversation_history if t.role == 'assistant'])
        
        return f"Session {self.session_id}: {total_turns} turns ({user_turns} user, {assistant_turns} assistant) - Last updated: {self.last_updated}"

class SessionContextManager:
    """Manager untuk mengelola session contexts."""
    
    def __init__(self, storage_path: str = "app/session_contexts.json"):
        self.storage_path = Path(storage_path)
        self.sessions: Dict[str, SessionContext] = {}
        self._load_sessions()
    
    def _load_sessions(self):
        """Load sessions dari file storage."""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for session_id, session_data in data.items():
                        # Convert conversation_history back to ConversationTurn objects
                        conversation_history = []
                        for turn_data in session_data.get('conversation_history', []):
                            turn = ConversationTurn(**turn_data)
                            conversation_history.append(turn)
                        
                        session_data['conversation_history'] = conversation_history
                        self.sessions[session_id] = SessionContext(**session_data)
                print(f"📁 Loaded {len(self.sessions)} session contexts")
            except Exception as e:
                print(f"❌ Error loading session contexts: {e}")
                self.sessions = {}
        else:
            print("📁 No existing session contexts found, starting fresh")
    
    def _save_sessions(self):
        """Save sessions ke file storage."""
        try:
            # Convert ConversationTurn objects to dicts for JSON serialization
            data = {}
            for session_id, session in self.sessions.items():
                session_dict = asdict(session)
                # Convert ConversationTurn objects to dicts
                conversation_history = []
                for turn in session.conversation_history:
                    conversation_history.append(asdict(turn))
                session_dict['conversation_history'] = conversation_history
                data[session_id] = session_dict
            
            with open(self.storage_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"💾 Saved {len(self.sessions)} session contexts")
        except Exception as e:
            print(f"❌ Error saving session contexts: {e}")
    
    def get_or_create_session(self, session_id: str) -> SessionContext:
        """Ambil atau buat session context baru."""
        if session_id not in self.sessions:
            self.sessions[session_id] = SessionContext(
                session_id=session_id,
                created_at=datetime.now().isoformat(),
                last_updated=datetime.now().isoformat(),
                conversation_history=[],
                user_preferences={},
                session_metadata={}
            )
            print(f"🆕 Created new session context: {session_id}")
        return self.sessions[session_id]
    
    def add_user_message(self, session_id: str, content: str, metadata: Optional[Dict[str, Any]] = None):
        """Tambahkan user message ke session."""
        session = self.get_or_create_session(session_id)
        session.add_turn('user', content, metadata=metadata)
        self._save_sessions()
        print(f"👤 Added user message to session {session_id}")
    
    def add_assistant_message(self, session_id: str, content: str, tool_calls: Optional[List[Dict[str, Any]]] = None, metadata: Optional[Dict[str, Any]] = None):
        """Tambahkan assistant message ke session."""
        session = self.get_or_create_session(session_id)
        session.add_turn('assistant', content, tool_calls=tool_calls, metadata=metadata)
        self._save_sessions()
        print(f"🤖 Added assistant message to session {session_id}")
    
    def get_session_context(self, session_id: str, max_turns: int = 10) -> str:
        """Ambil context string untuk session."""
        if session_id not in self.sessions:
            return f"No previous context for session {session_id}"
        
        session = self.sessions[session_id]
        recent_context = session.get_recent_context(max_turns)
        
        if not recent_context.strip():
            return f"Session {session_id} started - no conversation history yet"
        
        return f"=== CONVERSATION CONTEXT ===\n{recent_context}\n=== END CONTEXT ==="
    
    def get_session_summary(self, session_id: str) -> str:
        """Ambil summary session."""
        if session_id not in self.sessions:
            return f"Session {session_id} not found"
        
        return self.sessions[session_id].get_summary()
    
    def list_sessions(self) -> List[str]:
        """List semua session IDs."""
        return list(self.sessions.keys())
    
    def cleanup_old_sessions(self, max_age_hours: int = 24):
        """Cleanup sessions yang sudah lama tidak digunakan."""
        cutoff_time = datetime.now().timestamp() - (max_age_hours * 3600)
        sessions_to_remove = []
        
        for session_id, session in self.sessions.items():
            last_updated = datetime.fromisoformat(session.last_updated).timestamp()
            if last_updated < cutoff_time:
                sessions_to_remove.append(session_id)
        
        for session_id in sessions_to_remove:
            del self.sessions[session_id]
            print(f"🗑️ Cleaned up old session: {session_id}")
        
        if sessions_to_remove:
            self._save_sessions()

# Global instance
session_manager = SessionContextManager()
