#!/usr/bin/env python3
"""
Test Phase V with Real Multi-Item Image
"""

import requests
import json
import base64

def test_with_real_image():
    """Test with a real multi-item outfit image"""
    base_url = "https://ai-stylist-api.preview.emergentagent.com"
    
    # Get auth token
    auth_response = requests.post(f"{base_url}/api/v1/auth/dev-bypass")
    if auth_response.status_code != 200:
        print(f"❌ Auth failed: {auth_response.status_code}")
        return
    
    token = auth_response.json()['access_token']
    print("✅ Authentication successful")
    
    # Download a real outfit image from Unsplash
    print("🔄 Downloading real outfit image...")
    try:
        image_response = requests.get(
            "https://images.unsplash.com/photo-1603252109303-2751441dd157?w=900&q=80&auto=format&fit=crop",
            timeout=30
        )
        if image_response.status_code != 200:
            print(f"❌ Failed to download image: {image_response.status_code}")
            return
            
        image_bytes = image_response.content
        image_b64 = base64.b64encode(image_bytes).decode('ascii')
        print(f"✅ Downloaded image ({len(image_bytes)} bytes)")
        
    except Exception as e:
        print(f"❌ Image download error: {e}")
        return
    
    # Test analyze endpoint with real image
    analyze_data = {
        "image_base64": image_b64,
        "multi": True
    }
    
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    
    print("🔄 Testing analyze endpoint with real image (may take 30-60 seconds)...")
    response = requests.post(f"{base_url}/api/v1/closet/analyze", 
                           json=analyze_data, headers=headers, timeout=120)
    
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        
        # Check response structure
        has_items = 'items' in data and isinstance(data['items'], list)
        has_count = 'count' in data and isinstance(data['count'], int)
        items_count = len(data.get('items', []))
        
        print(f"\n🔍 Analysis Results:")
        print(f"Has 'items': {has_items}")
        print(f"Has 'count': {has_count}")
        print(f"Items count: {items_count}")
        
        if has_items and data['items']:
            for i, item in enumerate(data['items']):
                print(f"\n📦 Item {i+1}:")
                print(f"  Label: {item.get('label')}")
                print(f"  Kind: {item.get('kind')}")
                print(f"  BBox: {item.get('bbox')}")
                
                analysis = item.get('analysis', {})
                print(f"  Title: {analysis.get('title')}")
                print(f"  Category: {analysis.get('category')}")
                print(f"  Sub-category: {analysis.get('sub_category')}")
                print(f"  Colors: {len(analysis.get('colors', []))}")
                
        # Test if this would be considered multi-item
        is_multi_item = items_count > 1
        print(f"\n🎯 Multi-item detection: {is_multi_item}")
        
        # Test clean-background on first item if available
        if data['items']:
            print("\n🔄 Testing clean-background endpoint...")
            
            # First create a closet item
            first_item_analysis = data['items'][0]['analysis']
            item_data = {
                "title": first_item_analysis.get('title', 'Test Item'),
                "category": first_item_analysis.get('category') or 'top',
                "image_base64": image_b64
            }
            
            create_response = requests.post(f"{base_url}/api/v1/closet", 
                                          json=item_data, headers=headers)
            
            if create_response.status_code == 201:
                item_id = create_response.json()['id']
                print(f"✅ Created closet item: {item_id}")
                
                # Test clean-background
                clean_response = requests.post(f"{base_url}/api/v1/closet/{item_id}/clean-background", 
                                             headers=headers, timeout=90)
                
                print(f"Clean-background status: {clean_response.status_code}")
                
                if clean_response.status_code == 200:
                    clean_data = clean_response.json()
                    applied = clean_data.get('applied', False)
                    reason = clean_data.get('reason', 'N/A')
                    
                    print(f"✅ Clean-background response: applied={applied}, reason={reason}")
                    
                    if applied:
                        item = clean_data.get('item', {})
                        has_reconstructed = bool(item.get('reconstructed_image_url'))
                        print(f"  Has reconstructed image: {has_reconstructed}")
                else:
                    print(f"❌ Clean-background failed: {clean_response.text[:200]}")
            else:
                print(f"❌ Failed to create closet item: {create_response.status_code}")
                
    else:
        print(f"❌ Analyze request failed: {response.text[:500]}")

if __name__ == "__main__":
    test_with_real_image()