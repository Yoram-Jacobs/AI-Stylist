#!/usr/bin/env python3
"""
Debug Phase V Multi-Item Analysis Response
"""

import requests
import json
import base64

def debug_analyze_response():
    """Debug the analyze endpoint response structure"""
    base_url = "https://ai-stylist-api.preview.emergentagent.com"
    
    # Get auth token
    auth_response = requests.post(f"{base_url}/api/v1/auth/dev-bypass")
    if auth_response.status_code != 200:
        print(f"❌ Auth failed: {auth_response.status_code}")
        return
    
    token = auth_response.json()['access_token']
    print("✅ Authentication successful")
    
    # Test analyze endpoint
    test_image_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    
    analyze_data = {
        "image_base64": test_image_b64,
        "multi": True
    }
    
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    
    print("🔄 Testing analyze endpoint...")
    response = requests.post(f"{base_url}/api/v1/closet/analyze", 
                           json=analyze_data, headers=headers, timeout=120)
    
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print("\n📋 Response Structure:")
        print(json.dumps(data, indent=2)[:2000])  # First 2000 chars
        
        # Check specific fields
        print(f"\n🔍 Analysis:")
        print(f"Has 'items': {'items' in data}")
        print(f"Has 'count': {'count' in data}")
        
        if 'items' in data:
            items = data['items']
            print(f"Items count: {len(items)}")
            
            if items:
                first_item = items[0]
                print(f"\n📦 First Item Structure:")
                print(f"Keys: {list(first_item.keys())}")
                
                # Check required fields
                required_fields = ['analysis', 'crop_base64', 'bbox', 'label', 'kind']
                for field in required_fields:
                    has_field = field in first_item
                    print(f"Has '{field}': {has_field}")
                    
                    if field == 'analysis' and has_field:
                        analysis = first_item['analysis']
                        print(f"  Analysis keys: {list(analysis.keys())}")
                        print(f"  Has title: {'title' in analysis}")
                        print(f"  Has category: {'category' in analysis}")
    else:
        print(f"❌ Request failed: {response.text}")

if __name__ == "__main__":
    debug_analyze_response()