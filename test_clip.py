#!/usr/bin/env python3
"""
Test FashionCLIP embedding with a proper image
"""

import requests
import base64
import json

def create_test_image():
    """Create a proper RGB test image"""
    from PIL import Image
    import io
    
    # Create a 64x64 RGB image with some pattern
    img = Image.new('RGB', (64, 64), color='red')
    # Add some pattern
    for x in range(64):
        for y in range(64):
            if (x + y) % 10 < 5:
                img.putpixel((x, y), (0, 0, 255))  # Blue
    
    buffer = io.BytesIO()
    img.save(buffer, format='JPEG', quality=90)
    return base64.b64encode(buffer.getvalue()).decode('ascii')

def test_clip_embedding():
    # Get auth token
    auth_response = requests.post("https://ai-stylist-api.preview.emergentagent.com/api/v1/auth/dev-bypass")
    if auth_response.status_code != 200:
        print(f"❌ Auth failed: {auth_response.status_code}")
        return
    
    token = auth_response.json()['access_token']
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    
    # Create test image
    test_image_b64 = create_test_image()
    print(f"✅ Created test image ({len(test_image_b64)} chars)")
    
    # Test closet creation with image
    item_data = {
        "title": "Test RGB Image Item",
        "category": "Top",
        "image_base64": test_image_b64
    }
    
    print("🔄 Testing closet create with RGB image...")
    response = requests.post(
        "https://ai-stylist-api.preview.emergentagent.com/api/v1/closet",
        json=item_data,
        headers=headers,
        timeout=60
    )
    
    if response.status_code == 201:
        item_id = response.json().get('id')
        print(f"✅ Item created: {item_id}")
        
        # Check if embedding was created
        get_response = requests.get(
            f"https://ai-stylist-api.preview.emergentagent.com/api/v1/closet/{item_id}",
            headers=headers
        )
        
        if get_response.status_code == 200:
            item_data = get_response.json()
            has_embedding = 'clip_embedding' in item_data
            embedding_size = len(item_data.get('clip_embedding', []))
            clip_model = item_data.get('clip_model')
            
            print(f"✅ Retrieved item - Embedding: {has_embedding} ({embedding_size}d), Model: {clip_model}")
        else:
            print(f"❌ Failed to retrieve item: {get_response.status_code}")
    else:
        print(f"❌ Failed to create item: {response.status_code}, {response.text}")

if __name__ == "__main__":
    test_clip_embedding()