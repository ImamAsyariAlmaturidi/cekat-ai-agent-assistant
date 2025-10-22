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
        self.docs_table = "documents"
        self.embeddings_table = "documents"  # Using same table for simplicity
        
        logger.info("CekatDocsRAG initialized")
    
    
    def search_docs(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search for relevant Cekat documentation using vector similarity."""
        try:
            # Check if clients are available
            if not self.openai_client:
                logger.warning("OpenAI client not available")
                return []
            
            if not self.supabase:
                logger.warning("Supabase client not available - returning empty results")
                return []
            
            # Generate embedding for query using small model
            response = self.openai_client.embeddings.create(
                model="text-embedding-3-small",
                input=query
            )
            
            query_embedding = response.data[0].embedding
            
            # Search using Supabase RPC function - get top 10 documents
            result = self.supabase.rpc('match_documents', {
                'query_embedding': query_embedding,
                'match_threshold': 0.5,  # Lower threshold to get more results
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
            return []
    


# Global instance
cekat_docs_rag = CekatDocsRAG()

def get_cekat_docs_rag() -> CekatDocsRAG:
    """Get the global CekatDocsRAG instance."""
    return cekat_docs_rag