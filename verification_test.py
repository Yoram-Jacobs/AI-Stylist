#!/usr/bin/env python3
"""
Quick verification of specific requirements from the review request
"""

import requests
import json

BASE_URL = "https://ai-stylist-api.preview.emergentagent.com"

def get_dev_token():
    """Get dev token"""
    response = requests.post(f"{BASE_URL}/api/v1/auth/dev-bypass")
    if response.status_code == 200:
        return response.json()['access_token']
    return None

def test_fee_preview():
    """Test specific fee preview calculation"""
    print("🔍 Testing fee preview calculation...")
    response = requests.get(f"{BASE_URL}/api/v1/listings/fee-preview?list_price_cents=2500")
    
    if response.status_code == 200:
        data = response.json()
        expected = {
            "stripe_fee_cents": 102,
            "platform_fee_cents": 168,
            "seller_net_cents": 2230
        }
        
        print(f"✅ Fee Preview Response: {data}")
        
        for key, expected_value in expected.items():
            actual_value = data.get(key)
            if actual_value == expected_value:
                print(f"✅ {key}: {actual_value} (correct)")
            else:
                print(f"❌ {key}: {actual_value} (expected {expected_value})")
    else:
        print(f"❌ Fee preview failed: {response.status_code}")

def test_stylist_history():
    """Test stylist history structure"""
    token = get_dev_token()
    if not token:
        print("❌ Could not get dev token")
        return
        
    print("🔍 Testing stylist history...")
    headers = {'Authorization': f'Bearer {token}'}
    response = requests.get(f"{BASE_URL}/api/v1/stylist/history", headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        messages = data.get('messages', [])
        
        print(f"✅ History Response: Found {len(messages)} messages")
        
        if messages:
            roles = [msg.get('role') for msg in messages]
            unique_roles = set(roles)
            print(f"✅ Roles found: {unique_roles}")
            
            # Check structure
            for i, msg in enumerate(messages[:3]):  # Check first 3 messages
                role = msg.get('role')
                has_transcript = bool(msg.get('transcript'))
                has_payload = bool(msg.get('assistant_payload')) if role == 'assistant' else True
                print(f"  Message {i+1}: role={role}, transcript={has_transcript}, payload={has_payload}")
        else:
            print("ℹ️ No messages in history yet")
    else:
        print(f"❌ History failed: {response.status_code}")

def main():
    print("🚀 DressApp Phase 2 Verification Tests")
    print("=" * 50)
    
    test_fee_preview()
    print()
    test_stylist_history()

if __name__ == "__main__":
    main()