"""Debug test for listing retirement issue"""
import os
import requests

BACKEND_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://ai-stylist-api.preview.emergentagent.com')

def main():
    base_url = BACKEND_URL.rstrip('/')
    
    # 1. Get auth token
    print("1. Getting auth token...")
    resp = requests.post(f"{base_url}/api/v1/auth/dev-bypass")
    token = resp.json()['access_token']
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    print(f"   Token: {token[:20]}...")
    
    # 2. Create closet item with intent='swap'
    print("\n2. Creating closet item with intent='swap'...")
    resp = requests.post(
        f"{base_url}/api/v1/closet",
        json={"title": "Debug Test Item", "category": "Top", "marketplace_intent": "swap", "condition": "good"},
        headers=headers
    )
    item = resp.json()
    item_id = item['id']
    listing_id = item.get('auto_listing_id')
    print(f"   Item ID: {item_id}")
    print(f"   Listing ID: {listing_id}")
    print(f"   marketplace_intent: {item.get('marketplace_intent')}")
    print(f"   source: {item.get('source')}")
    
    # 3. Get the listing to check auto_created field
    print("\n3. Getting listing details...")
    resp = requests.get(f"{base_url}/api/v1/listings/{listing_id}", headers=headers)
    listing = resp.json()
    print(f"   Listing status: {listing.get('status')}")
    print(f"   Listing mode: {listing.get('mode')}")
    print(f"   Listing auto_created: {listing.get('auto_created')}")
    
    # 4. Update intent to 'own'
    print("\n4. Updating intent to 'own'...")
    resp = requests.patch(
        f"{base_url}/api/v1/closet/{item_id}",
        json={"marketplace_intent": "own"},
        headers=headers
    )
    updated_item = resp.json()
    print(f"   Updated marketplace_intent: {updated_item.get('marketplace_intent')}")
    print(f"   Updated source: {updated_item.get('source')}")
    print(f"   Updated auto_listing_id: {updated_item.get('auto_listing_id')}")
    
    # 5. Get the listing again to check if it was retired
    print("\n5. Getting listing after intent change...")
    resp = requests.get(f"{base_url}/api/v1/listings/{listing_id}", headers=headers)
    listing_after = resp.json()
    print(f"   Listing status: {listing_after.get('status')}")
    print(f"   Expected: removed")
    
    if listing_after.get('status') == 'removed':
        print("\n✅ SUCCESS: Listing was correctly retired")
    else:
        print(f"\n❌ FAILURE: Listing status is '{listing_after.get('status')}', expected 'removed'")
        print("\nFull listing after update:")
        print(listing_after)

if __name__ == "__main__":
    main()
