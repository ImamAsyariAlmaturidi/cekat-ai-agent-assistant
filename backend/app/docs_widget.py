"""Widget untuk menampilkan dokumentasi dengan format yang rapi."""

from typing import Dict, Any, Optional
from dataclasses import dataclass

@dataclass
class DocsWidgetData:
    """Data untuk docs widget."""
    title: str
    content: str
    url_link: Optional[str] = None
    hint: Optional[str] = None
    size: str = "md"  # sm, md, lg

def create_docs_widget(
    title: str,
    content: str,
    url_link: Optional[str] = None,
    hint: Optional[str] = None,
    size: str = "md"
) -> Dict[str, Any]:
    """
    Membuat widget dokumentasi dengan format yang rapi.
    
    Args:
        title: Judul dokumentasi
        content: Konten dalam format markdown
        url_link: URL link opsional
        hint: Hint/tipe dokumentasi opsional
        size: Ukuran widget (sm, md, lg)
    
    Returns:
        Dict dengan struktur widget untuk frontend
    """
    
    widget_data = {
        "type": "docs_widget",
        "size": size,
        "data": {
            "title": title,
            "content": content,
            "url_link": url_link,
            "hint": hint or "Documentation"
        },
        "layout": {
            "header": {
                "hint": hint or "Documentation",
                "url_link": url_link
            },
            "content": {
                "title": title,
                "markdown_content": content
            }
        }
    }
    
    return widget_data

def create_cekat_docs_widget(
    title: str,
    content: str,
    feature_type: str = "Feature",
    url_link: Optional[str] = None
) -> Dict[str, Any]:
    """
    Membuat widget dokumentasi khusus untuk Cekat.
    
    Args:
        title: Judul fitur
        content: Konten dokumentasi
        feature_type: Tipe fitur (Feature, API, Workflow, etc.)
        url_link: URL ke halaman fitur
    
    Returns:
        Dict dengan struktur widget Cekat docs
    """
    
    widget_data = create_docs_widget(
        title=title,
        content=content,
        url_link=url_link,
        hint=f"Cekat {feature_type}",
        size="lg"
    )
    
    # Add feature_type to data
    widget_data["data"]["feature_type"] = feature_type
    
    return widget_data

def create_workflow_docs_widget(
    workflow_name: str,
    description: str,
    steps: list[str],
    url_link: Optional[str] = None
) -> Dict[str, Any]:
    """
    Membuat widget dokumentasi khusus untuk workflows.
    
    Args:
        workflow_name: Nama workflow
        description: Deskripsi workflow
        steps: Daftar langkah-langkah
        url_link: URL ke halaman workflow
    
    Returns:
        Dict dengan struktur widget workflow docs
    """
    
    content = f"""**{workflow_name}**

{description}

**Langkah-langkah:**
"""
    
    for i, step in enumerate(steps, 1):
        content += f"{i}. {step}\n"
    
    return create_cekat_docs_widget(
        title=f"Workflow: {workflow_name}",
        content=content,
        feature_type="Workflow",
        url_link=url_link
    )

def create_api_docs_widget(
    api_name: str,
    description: str,
    endpoint: str,
    method: str = "GET",
    parameters: Optional[Dict[str, str]] = None,
    url_link: Optional[str] = None
) -> Dict[str, Any]:
    """
    Membuat widget dokumentasi khusus untuk API.
    
    Args:
        api_name: Nama API
        description: Deskripsi API
        endpoint: Endpoint URL
        method: HTTP method
        parameters: Parameter API
        url_link: URL ke dokumentasi API
    
    Returns:
        Dict dengan struktur widget API docs
    """
    
    content = f"""**{api_name}**

{description}

**Endpoint:** `{method} {endpoint}`

"""
    
    if parameters:
        content += "**Parameters:**\n"
        for param, desc in parameters.items():
            content += f"- `{param}`: {desc}\n"
    
    return create_cekat_docs_widget(
        title=f"API: {api_name}",
        content=content,
        feature_type="API",
        url_link=url_link
    )

# Contoh penggunaan
if __name__ == "__main__":
    # Contoh workflow docs
    workflow_widget = create_workflow_docs_widget(
        workflow_name="Customer Onboarding",
        description="Workflow untuk onboarding customer baru",
        steps=[
            "Terima data customer",
            "Validasi informasi",
            "Kirim email welcome",
            "Setup akun customer"
        ],
        url_link="https://chat.cekat.ai/workflows"
    )
    
    print("Workflow Widget:", workflow_widget)
    
    # Contoh API docs
    api_widget = create_api_docs_widget(
        api_name="Create Customer",
        description="API untuk membuat customer baru",
        endpoint="/api/customers",
        method="POST",
        parameters={
            "name": "Nama customer",
            "email": "Email customer",
            "phone": "Nomor telepon"
        },
        url_link="https://chat.cekat.ai/developers/api-tools"
    )
    
    print("\nAPI Widget:", api_widget)
