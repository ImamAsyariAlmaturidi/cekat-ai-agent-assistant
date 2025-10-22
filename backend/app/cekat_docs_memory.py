"""Tool untuk mencari dokumen Cekat menggunakan endpoint webhook n8n.

Tool ini menghubungi endpoint webhook n8n untuk mencari informasi dokumen Cekat.
Endpoint: https://n8n.cekat.ai/webhook/cekat/ask
Method: POST
Body: {"chatInput": "query dari user", "sessionId": "session_id_dari_chatkit"}

Contoh penggunaan:
    from cekat_docs_memory import search_cekat_docs
    
    result = search_cekat_docs("bagaimana cara setup AI Agent?", "session_123")
    print(result)
"""

import requests
import json
from typing import Dict, Any, Optional


def cekat_docs_memory(query: str, session_id: str = None) -> Dict[str, Any]:
    """
    Mencari dokumen Cekat menggunakan endpoint webhook n8n.
    
    Args:
        query (str): Query pencarian dari user
        session_id (str, optional): Session ID dari chatkit session
        
    Returns:
        Dict[str, Any]: Response dari webhook n8n atau error message
    """
    try:
        # URL endpoint webhook n8n
        webhook_url = "https://n8n.cekat.ai/webhook/cekat/ask"
        
        # Payload untuk POST request
        payload = {
            "chatInput": query
        }
        
        # Tambahkan sessionId jika ada
        if session_id:
            payload["sessionId"] = session_id
        
        # Headers untuk request
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        # Kirim POST request ke webhook
        response = requests.post(
            webhook_url,
            json=payload,
            headers=headers,
            timeout=30  # Timeout 30 detik
        )
        
        # Cek status code
        if response.status_code == 200:
            try:
                # Parse JSON response
                result = response.json()
                return {
                    "success": True,
                    "data": result,
                    "status_code": response.status_code
                }
            except json.JSONDecodeError:
                # Jika response bukan JSON, return text
                return {
                    "success": True,
                    "data": response.text,
                    "status_code": response.status_code
                }
        else:
            # Handle error status codes
            return {
                "success": False,
                "error": f"HTTP {response.status_code}: {response.text}",
                "status_code": response.status_code
            }
            
    except requests.exceptions.Timeout:
        return {
            "success": False,
            "error": "Request timeout - webhook tidak merespons dalam 30 detik",
            "status_code": None
        }
    except requests.exceptions.ConnectionError:
        return {
            "success": False,
            "error": "Connection error - tidak dapat terhubung ke webhook",
            "status_code": None
        }
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "error": f"Request error: {str(e)}",
            "status_code": None
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}",
            "status_code": None
        }


def search_cekat_docs(query: str, session_id: str = None) -> str:
    """
    Fungsi wrapper untuk mencari dokumen Cekat.
    Mengembalikan string response yang siap digunakan.
    
    Args:
        query (str): Query pencarian dari user
        session_id (str, optional): Session ID dari chatkit session
        
    Returns:
        str: Hasil pencarian atau error message
    """
    result = cekat_docs_memory(query, session_id)
    
    if result["success"]:
        # Jika berhasil, format response
        data = result["data"]
        
        # Jika data adalah dict, coba extract informasi yang relevan
        if isinstance(data, dict):
            # Coba ambil field yang umum ada di response
            if "answer" in data:
                return data["answer"]
            elif "response" in data:
                return data["response"]
            elif "result" in data:
                return data["result"]
            elif "message" in data:
                return data["message"]
            else:
                # Jika tidak ada field yang dikenal, return JSON string
                return json.dumps(data, indent=2, ensure_ascii=False)
        else:
            # Jika data bukan dict, return langsung
            return str(data)
    else:
        # Jika error, return error message
        return f"❌ Error mencari dokumen: {result['error']}"


# Test function untuk debugging
if __name__ == "__main__":
    # Test dengan query sederhana dan sessionId
    test_query = "bagaimana cara setup AI Agent di Cekat?"
    test_session_id = "test_session_123"
    print(f"Testing dengan query: {test_query}")
    print(f"Testing dengan sessionId: {test_session_id}")
    print("-" * 50)
    
    result = search_cekat_docs(test_query, test_session_id)
    print(result)
