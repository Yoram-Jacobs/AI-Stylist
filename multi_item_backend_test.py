#!/usr/bin/env python3
"""
DressApp Multi-Item Outfit Extraction Backend Testing
Tests the new multi-item detection and analysis feature.
"""

import requests
import sys
import json
import base64
from typing import Dict, Any

class MultiItemAPITester:
    def __init__(self, base_url: str = "https://ai-stylist-api.preview.emergentagent.com"):
        self.base_url = base_url.rstrip('/')
        self.dev_token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []

    def log_test(self, name: str, success: bool, details: str = ""):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {name}")
        else:
            self.failed_tests.append({"test": name, "details": details})
            print(f"❌ {name} - {details}")

    def make_request(self, method: str, endpoint: str, data: Any = None, 
                    token: str = None, timeout: int = 90) -> tuple[bool, Dict, int]:
        """Make HTTP request with error handling"""
        url = f"{self.base_url}/api/v1{endpoint}"
        headers = {'Content-Type': 'application/json'}
        
        if token:
            headers['Authorization'] = f'Bearer {token}'

        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=timeout)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=timeout)
            else:
                return False, {}, 0

            try:
                response_data = response.json() if response.content else {}
            except:
                response_data = {"raw_response": response.text}
            
            return True, response_data, response.status_code
        except Exception as e:
            return False, {"error": str(e)}, 0

    def setup_auth(self):
        """Get dev token for testing"""
        success, data, status = self.make_request('POST', '/auth/dev-bypass')
        if success and status == 200 and 'access_token' in data:
            self.dev_token = data['access_token']
            self.log_test("Setup Auth", True, f"Got token for {data.get('user', {}).get('email')}")
            return True
        else:
            self.log_test("Setup Auth", False, f"Status: {status}, Data: {data}")
            return False

    def test_multi_item_analyze_with_multi_true(self):
        """Test POST /closet/analyze with multi=true"""
        if not self.dev_token:
            self.log_test("Multi-Item Analyze (multi=true)", False, "No dev token available")
            return None

        # Use a small test image (1x1 pixel PNG)
        test_image_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
        
        analyze_data = {
            "image_base64": test_image_b64,
            "multi": True
        }
        
        print("🔄 Testing multi-item analysis (multi=true) - this may take 25-45 seconds...")
        success, data, status = self.make_request('POST', '/closet/analyze', analyze_data, token=self.dev_token, timeout=90)
        
        if success and status == 200:
            # Check required fields for multi-item response
            has_items_array = 'items' in data and isinstance(data['items'], list)
            has_count = 'count' in data and isinstance(data['count'], int)
            items_count_matches = data.get('count') == len(data.get('items', []))
            items_count_gte_1 = data.get('count', 0) >= 1
            
            # Check each item in the array has required fields
            items_valid = True
            if has_items_array and data['items']:
                for item in data['items']:
                    required_fields = ['label', 'kind', 'bbox', 'crop_base64', 'crop_mime', 'analysis']
                    if not all(field in item for field in required_fields):
                        items_valid = False
                        break
                    
                    # Check bbox is array of 4 integers
                    bbox = item.get('bbox', [])
                    if not (isinstance(bbox, list) and len(bbox) == 4 and all(isinstance(x, int) for x in bbox)):
                        items_valid = False
                        break
                    
                    # Check crop_base64 is non-empty string
                    if not isinstance(item.get('crop_base64'), str) or len(item.get('crop_base64', '')) == 0:
                        items_valid = False
                        break
                    
                    # Check analysis has required fields
                    analysis = item.get('analysis', {})
                    if not isinstance(analysis, dict) or not analysis.get('title'):
                        items_valid = False
                        break

            # Check backwards compatibility - top-level fields should mirror first item
            has_top_level_fields = 'title' in data and 'category' in data
            
            all_valid = (has_items_array and has_count and items_count_matches and 
                        items_count_gte_1 and items_valid and has_top_level_fields)
            
            details = f"Items: {data.get('count', 0)}, Valid structure: {items_valid}, Top-level fields: {has_top_level_fields}"
            self.log_test("Multi-Item Analyze (multi=true)", all_valid, details)
            
            return data
        else:
            self.log_test("Multi-Item Analyze (multi=true)", False, f"Status: {status}, Data: {data}")
            return None

    def test_multi_item_analyze_with_multi_false(self):
        """Test POST /closet/analyze with multi=false for backwards compatibility"""
        if not self.dev_token:
            self.log_test("Multi-Item Analyze (multi=false)", False, "No dev token available")
            return None

        test_image_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
        
        analyze_data = {
            "image_base64": test_image_b64,
            "multi": False
        }
        
        print("🔄 Testing single-item analysis (multi=false) for backwards compatibility...")
        success, data, status = self.make_request('POST', '/closet/analyze', analyze_data, token=self.dev_token, timeout=90)
        
        if success and status == 200:
            # Should return single-item array + legacy top-level fields
            has_items_array = 'items' in data and isinstance(data['items'], list)
            items_count_is_1 = len(data.get('items', [])) == 1
            has_count_1 = data.get('count') == 1
            
            # Check the single item structure
            single_item_valid = False
            if has_items_array and data['items']:
                item = data['items'][0]
                required_fields = ['label', 'kind', 'bbox', 'crop_base64', 'crop_mime', 'analysis']
                single_item_valid = all(field in item for field in required_fields)
            
            # Check legacy top-level fields are present
            has_legacy_fields = all(field in data for field in ['title', 'category'])
            
            all_valid = (has_items_array and items_count_is_1 and has_count_1 and 
                        single_item_valid and has_legacy_fields)
            
            details = f"Items count: {len(data.get('items', []))}, Legacy fields: {has_legacy_fields}"
            self.log_test("Multi-Item Analyze (multi=false)", all_valid, details)
            
            return data
        else:
            self.log_test("Multi-Item Analyze (multi=false)", False, f"Status: {status}, Data: {data}")
            return None

    def test_analyze_auth_required(self):
        """Test that analyze endpoint requires auth (401 without token)"""
        test_image_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
        
        analyze_data = {
            "image_base64": test_image_b64,
            "multi": True
        }
        
        success, data, status = self.make_request('POST', '/closet/analyze', analyze_data)  # No token
        
        auth_required = status == 401
        self.log_test("Analyze Auth Required", auth_required, f"Status: {status} (expected 401)")

    def test_analyze_bad_base64_rejection(self):
        """Test that analyze endpoint rejects bad base64 with 400"""
        if not self.dev_token:
            self.log_test("Analyze Bad Base64 Rejection", False, "No dev token available")
            return

        analyze_data = {
            "image_base64": "invalid_base64_string_that_cannot_be_decoded",
            "multi": True
        }
        
        success, data, status = self.make_request('POST', '/closet/analyze', analyze_data, token=self.dev_token)
        
        bad_base64_rejected = status == 400
        self.log_test("Analyze Bad Base64 Rejection", bad_base64_rejected, f"Status: {status} (expected 400)")

    def test_save_items_with_crop_base64(self):
        """Test saving items using returned crop_base64 works"""
        if not self.dev_token:
            self.log_test("Save Items with Crop Base64", False, "No dev token available")
            return

        # First get analysis results
        analyze_result = self.test_multi_item_analyze_with_multi_true()
        if not analyze_result or not analyze_result.get('items'):
            self.log_test("Save Items with Crop Base64", False, "No analysis results to test with")
            return

        # Try to save the first item using its crop_base64
        first_item = analyze_result['items'][0]
        analysis = first_item.get('analysis', {})
        
        item_data = {
            "title": analysis.get('title', 'Test Multi-Item Save'),
            "category": analysis.get('category', 'Top'),
            "sub_category": analysis.get('sub_category'),
            "item_type": analysis.get('item_type'),
            "brand": analysis.get('brand'),
            "gender": analysis.get('gender'),
            "dress_code": analysis.get('dress_code'),
            "season": analysis.get('season', []),
            "colors": analysis.get('colors', []),
            "fabric_materials": analysis.get('fabric_materials', []),
            "pattern": analysis.get('pattern'),
            "state": analysis.get('state'),
            "condition": analysis.get('condition'),
            "quality": analysis.get('quality'),
            "tags": analysis.get('tags', []),
            "image_base64": first_item.get('crop_base64'),
            "image_mime": first_item.get('crop_mime', 'image/jpeg'),
            "marketplace_intent": "own"
        }
        
        # Remove None values
        item_data = {k: v for k, v in item_data.items() if v is not None}
        
        success, data, status = self.make_request('POST', '/closet', item_data, token=self.dev_token)
        
        if success and status == 201:
            item_id = data.get('id')
            has_id = bool(item_id)
            title_matches = data.get('title') == item_data.get('title')
            
            self.log_test("Save Items with Crop Base64", has_id and title_matches, 
                         f"Created item: {item_id}, Title: {data.get('title')}")
            
            return item_id
        else:
            self.log_test("Save Items with Crop Base64", False, f"Status: {status}, Data: {data}")
            return None

    def test_marketplace_intent_listing_creation(self):
        """Test that marketplace_intent creates listings when appropriate"""
        if not self.dev_token:
            self.log_test("Marketplace Intent Listing Creation", False, "No dev token available")
            return

        # Get analysis results first
        analyze_result = self.test_multi_item_analyze_with_multi_true()
        if not analyze_result or not analyze_result.get('items'):
            self.log_test("Marketplace Intent Listing Creation", False, "No analysis results to test with")
            return

        first_item = analyze_result['items'][0]
        analysis = first_item.get('analysis', {})
        
        # Create item with for_sale intent
        item_data = {
            "title": analysis.get('title', 'Test For Sale Multi-Item'),
            "category": analysis.get('category', 'Top'),
            "price_cents": 5000,
            "marketplace_intent": "for_sale",
            "condition": "good",
            "image_base64": first_item.get('crop_base64'),
            "image_mime": first_item.get('crop_mime', 'image/jpeg')
        }
        
        success, data, status = self.make_request('POST', '/closet', item_data, token=self.dev_token)
        
        if success and status == 201:
            has_listing_id = data.get('listing_id') is not None
            source_shared = data.get('source') == 'Shared'
            
            if has_listing_id:
                # Verify listing was created
                listing_id = data.get('listing_id')
                success2, listing_data, status2 = self.make_request('GET', f'/listings/{listing_id}')
                
                if success2 and status2 == 200:
                    listing_valid = (listing_data.get('mode') == 'sell' and 
                                   listing_data.get('financial_metadata', {}).get('list_price_cents') == 5000)
                    
                    all_valid = has_listing_id and source_shared and listing_valid
                    self.log_test("Marketplace Intent Listing Creation", all_valid, 
                                 f"Listing ID: {listing_id}, Mode: {listing_data.get('mode')}")
                else:
                    self.log_test("Marketplace Intent Listing Creation", False, f"Could not retrieve listing: {status2}")
            else:
                self.log_test("Marketplace Intent Listing Creation", False, "No listing ID created")
        else:
            self.log_test("Marketplace Intent Listing Creation", False, f"Status: {status}, Data: {data}")

    def run_all_tests(self):
        """Run all multi-item backend tests"""
        print("🚀 Starting DressApp Multi-Item Backend Tests")
        print("=" * 60)
        
        if not self.setup_auth():
            print("❌ Could not setup authentication, aborting tests")
            return False
        
        # Core multi-item functionality tests
        self.test_multi_item_analyze_with_multi_true()
        self.test_multi_item_analyze_with_multi_false()
        
        # Security and validation tests
        self.test_analyze_auth_required()
        self.test_analyze_bad_base64_rejection()
        
        # Integration tests
        self.test_save_items_with_crop_base64()
        self.test_marketplace_intent_listing_creation()
        
        # Print summary
        print("\n" + "=" * 60)
        print(f"📊 Multi-Item Backend Tests Summary")
        print(f"Tests run: {self.tests_run}")
        print(f"Tests passed: {self.tests_passed}")
        print(f"Success rate: {(self.tests_passed/self.tests_run*100):.1f}%")
        
        if self.failed_tests:
            print(f"\n❌ Failed tests:")
            for test in self.failed_tests:
                print(f"  - {test['test']}: {test['details']}")
        
        return self.tests_passed == self.tests_run

def main():
    tester = MultiItemAPITester()
    success = tester.run_all_tests()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())