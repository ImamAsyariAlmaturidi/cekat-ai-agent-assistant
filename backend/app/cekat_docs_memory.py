"""Cekat Docs RAG System using Supabase with pgvector for semantic search."""

import os
import logging
from typing import List, Dict, Any, Optional

from supabase import create_client, Client
from openai import OpenAI

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CekatDocsRAG:
    """RAG system for retrieving Cekat documentation using Supabase pgvector."""
    
    def __init__(self):
        """Initialize Supabase client and OpenAI client."""
        # Supabase configuration
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_ANON_KEY")
        
        # Check if Supabase is configured
        if not self.supabase_url or not self.supabase_key:
            logger.warning("Supabase not configured - URL or key missing")
            logger.info("Set SUPABASE_URL and SUPABASE_ANON_KEY environment variables to enable Supabase")
        
        # Initialize clients with error handling
        if self.supabase_url and self.supabase_key:
            try:
                self.supabase: Client = create_client(self.supabase_url, self.supabase_key)
                logger.info("Supabase client initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Supabase client: {e}")
                self.supabase = None
        else:
            logger.warning("Supabase not configured, setting client to None")
            self.supabase = None
        
        try:
            openai_key = os.getenv("OPENAI_API_KEY")
            if openai_key:
                self.openai_client = OpenAI(api_key=openai_key)
                logger.info("OpenAI client initialized")
            else:
                logger.warning("OpenAI API key not found, embeddings will not work")
                self.openai_client = None
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}")
            self.openai_client = None
        
        # Table names
        self.docs_table = "cekat_docs"
        self.embeddings_table = "cekat_docs_embeddings"
        
        logger.info("CekatDocsRAG initialized")
    
    
    def search_docs(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search for relevant Cekat documentation using vector similarity."""
        try:
            # Check if clients are available
            if not self.openai_client:
                logger.warning("OpenAI client not available, using fallback search")
                return self._fallback_search(query, limit)
            
            if not self.supabase:
                logger.error("Supabase client not available")
                return [{
                    "title": "Supabase Not Configured",
                    "content": "Supabase is not configured. Please set SUPABASE_URL and SUPABASE_ANON_KEY environment variables to enable document search.",
                    "url": "",
                    "category": "system",
                    "similarity": 0
                }]
            
            # Generate embedding for query
            response = self.openai_client.embeddings.create(
                model="text-embedding-ada-002",
                input=query
            )
            
            query_embedding = response.data[0].embedding
            
            # Search using Supabase RPC function (assuming it exists)
            result = self.supabase.rpc('search_cekat_docs', {
                'query_embedding': query_embedding,
                'match_threshold': 0.7,
                'match_count': limit
            }).execute()
            
            if result.data:
                logger.info(f"Found {len(result.data)} relevant documents")
                return result.data
            else:
                logger.info("No relevant documents found")
                return []
                
        except Exception as e:
            logger.error(f"Error searching documents: {e}")
            # Fallback to simple text search if vector search fails
            return self._fallback_search(query, limit)
    
    def _fallback_search(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Fallback text search if vector search is not available."""
        try:
            if not self.supabase:
                logger.error("Supabase client not available for fallback search")
                return [{
                    "title": "Supabase Not Configured",
                    "content": "Supabase is not configured. Please set SUPABASE_URL and SUPABASE_ANON_KEY environment variables to enable document search.",
                    "url": "",
                    "category": "system",
                    "similarity": 0
                }]
                
            # Simple text search using Supabase
            result = self.supabase.table(self.docs_table).select("*").ilike("content", f"%{query}%").limit(limit).execute()
            
            if result.data:
                logger.info(f"Fallback search found {len(result.data)} documents")
                return result.data
            else:
                return []
                
        except Exception as e:
            logger.error(f"Error in fallback search: {e}")
            return []


# Global instance
cekat_docs_rag = CekatDocsRAG()

def get_cekat_docs_rag() -> CekatDocsRAG:
    """Get the global CekatDocsRAG instance."""
    return cekat_docs_rag