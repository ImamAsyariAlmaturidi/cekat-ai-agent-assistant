#!/usr/bin/env python3
"""Test untuk memverifikasi AI memberikan penjelasan saat navigate."""

import asyncio
import sys
import os
from datetime import datetime

# Add the backend directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from app.server import FactAssistantServer
from chatkit.types import UserMessageItem, ThreadMetadata

async def test_navigation_explanation():
    """Test apakah AI memberikan penjelasan saat navigate."""
    print("🧭 Testing Navigation Explanation...")
    print("=" * 60)
    
    # Create server instance
    server = FactAssistantServer()
    print("✅ Server created")
    
    # Create test thread
    thread = ThreadMetadata(
        id="navigation_test",
        created_at=datetime.now()
    )
    
    # Save thread
    await server.store.save_thread(thread, {})
    print("✅ Thread saved")
    
    # Test workflows navigation dengan pertanyaan yang membutuhkan penjelasan
    test_message = "Cara bikin workflows di cekat gimana"
    
    print(f"\n❓ Test Question: {test_message}")
    print("-" * 40)
    
    user_message = UserMessageItem(
        id="navigation_test_msg",
        thread_id=thread.id,
        created_at=datetime.now(),
        content=[{"type": "input_text", "text": test_message}],
        inference_options={}
    )
    
    await server.store.add_thread_item(thread.id, user_message, {})
    print(f"👤 User: {test_message}")
    
    print("🤖 AI: Processing message...")
    
    try:
        response_events = []
        async for event in server.respond(thread, user_message, {}):
            response_events.append(event)
        
        print(f"✅ Message processed with {len(response_events)} events")
        print("🔍 Check console output above to see if AI provides explanation before navigation")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    
    print("-" * 40)
    print("🎉 Navigation explanation test completed!")

async def main():
    """Main test function."""
    await test_navigation_explanation()

if __name__ == "__main__":
    asyncio.run(main())
