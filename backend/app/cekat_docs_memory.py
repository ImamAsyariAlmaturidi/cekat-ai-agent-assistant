"""Cekat Docs RAG System using Supabase with pgvector for semantic search."""

import os
import logging
import hashlib
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from supabase import create_client, Client
from openai import OpenAI


# Configure logging - set to WARNING to reduce noise
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

class CekatDocsRAG:
    """RAG system for retrieving Cekat documentation using Supabase pgvector."""
    
    def __init__(self):
        """Initialize Supabase client and OpenAI client."""
        # Supabase configuration
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_ANON_KEY")
        
        # Initialize query cache for faster response
        self.query_cache = {}
        self.max_cache_size = 100  # Limit cache to prevent memory issues
        
        # Check if Supabase is configured
        if not self.supabase_url or not self.supabase_key:
            logger.warning("Supabase not configured - URL or key missing")
            logger.info("Set SUPABASE_URL and SUPABASE_ANON_KEY environment variables to enable Supabase")
        
        # Initialize clients with error handling
        if self.supabase_url and self.supabase_key:
            try:
                self.supabase: Client = create_client(self.supabase_url, self.supabase_key)
                # Supabase initialized silently
                pass
            except Exception as e:
                # Error logged silently
                pass
                self.supabase = None
        else:
            logger.warning("Supabase not configured, setting client to None")
            self.supabase = None
        
        try:
            openai_key = os.getenv("OPENAI_API_KEY")
            if openai_key:
                self.openai_client = OpenAI(api_key=openai_key)
                # OpenAI initialized silently
                pass
            else:
                # Warning logged silently
                pass
                self.openai_client = None
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}")
            self.openai_client = None
        
        # Table names
        self.docs_table = "documents"
        self.embeddings_table = "documents"  # Using same table for simplicity
        
        # Initialized silently for performance
    
    
    def search_docs(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search for relevant Cekat documentation using vector similarity with caching."""
        try:
            # Check if clients are available
            if not self.openai_client:
                logger.warning("OpenAI client not available")
                return []
            
            if not self.supabase:
                logger.warning("Supabase client not available - returning empty results")
                return []
            
            # Generate cache key from query
            query_normalized = query.lower().strip()
            query_hash = hashlib.md5(f"{query_normalized}_{limit}".encode()).hexdigest()
            
            # Check cache first
            if query_hash in self.query_cache:
                # Cache hit - return silently
                return self.query_cache[query_hash]
            
            # Generate embedding for query using small model
            response = self.openai_client.embeddings.create(
                model="text-embedding-3-small",
                input=query
            )
            
            query_embedding = response.data[0].embedding
            
            # Search using Supabase RPC function - default to 5 for faster response
            result = self.supabase.rpc('match_documents', {
                'query_embedding': query_embedding,
                'match_count': limit,
                'filter': {}  # Empty filter to get all documents
            }).execute()
            
            if result.data:
                # Found documents silently
                pass
                
                # Cache the results
                if len(self.query_cache) >= self.max_cache_size:
                    # Remove oldest entry (simple FIFO)
                    self.query_cache.pop(next(iter(self.query_cache)))
                
                self.query_cache[query_hash] = result.data
                return result.data
            else:
                # No documents found silently
                return []
                
        except Exception as e:
            logger.error(f"Error searching documents: {e}")
            return []
    


# Global instance
cekat_docs_rag = CekatDocsRAG()

def get_cekat_docs_rag() -> CekatDocsRAG:
    """Get the global CekatDocsRAG instance."""
    return cekat_docs_rag