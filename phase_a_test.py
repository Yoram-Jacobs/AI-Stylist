#!/usr/bin/env python3
"""
DressApp Phase A Architecture Testing
Tests the new Phase A features: FashionCLIP embeddings, closet search, and garment vision regression.
"""

import requests
import sys
import json
import time
import base64
from datetime import datetime
from typing import Dict, Any, Optional

class PhaseAAPITester:
    def __init__(self, base_url: str = "https://ai-stylist-api.preview.emergentagent.com"):
        self.base_url = base_url.rstrip('/')
        self.dev_token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/json'})

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
                    token: str = None, timeout: int = 30) -> tuple[bool, Dict, int]:
        """Make HTTP request with error handling"""
        url = f"{self.base_url}/api/v1{endpoint}"
        headers = {}
        
        if token:
            headers['Authorization'] = f'Bearer {token}'
        
        headers.update(self.session.headers)

        try:
            if method == 'GET':
                response = self.session.get(url, headers=headers, timeout=timeout)
            elif method == 'POST':
                response = self.session.post(url, json=data, headers=headers, timeout=timeout)
            elif method == 'PATCH':
                response = self.session.patch(url, json=data, headers=headers, timeout=timeout)
            elif method == 'DELETE':
                response = self.session.delete(url, headers=headers, timeout=timeout)
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
            print(f"✅ Authenticated as {data.get('user', {}).get('email')}")
            return True
        else:
            print(f"❌ Authentication failed: {status}, {data}")
            return False

    def test_closet_analyze_regression_multi_true(self):
        """REGRESSION: Test POST /api/v1/closet/analyze with multi=true (default)"""
        if not self.dev_token:
            self.log_test("Closet Analyze Regression Multi True", False, "No dev token available")
            return
            
        # Use a small test image
        test_image_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
        
        analyze_data = {
            "image_base64": test_image_b64,
            "multi": True  # Explicit multi=true
        }
        
        print("🔄 Testing analyze regression with multi=true (this may take 10-45 seconds)...")
        success, data, status = self.make_request('POST', '/closet/analyze', analyze_data, token=self.dev_token, timeout=90)
        
        if success and status == 200:
            # Check response contract unchanged
            has_items = 'items' in data and isinstance(data['items'], list)
            has_count = 'count' in data
            has_legacy_fields = 'title' in data and 'category' in data  # Legacy mirror
            
            # Check items structure
            items_valid = True
            if data.get('items'):
                for item in data['items']:
                    analysis = item.get('analysis', {})
                    if not (analysis.get('title') and analysis.get('category') and 'model_used' in analysis):
                        items_valid = False
                        break
                        
            # Check model_used is gemini-*
            model_used = data.get('model_used', '')
            is_gemini_model = model_used.startswith('gemini-')
            
            all_valid = has_items and has_count and has_legacy_fields and items_valid and is_gemini_model
            self.log_test("Closet Analyze Regression Multi True", all_valid, 
                         f"Items: {len(data.get('items', []))}, Count: {data.get('count')}, Model: {model_used}")
        else:
            self.log_test("Closet Analyze Regression Multi True", False, f"Status: {status}, Data: {data}")

    def test_closet_analyze_regression_multi_false(self):
        """REGRESSION: Test POST /api/v1/closet/analyze with multi=false"""
        if not self.dev_token:
            self.log_test("Closet Analyze Regression Multi False", False, "No dev token available")
            return
            
        test_image_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
        
        analyze_data = {
            "image_base64": test_image_b64,
            "multi": False  # Single analysis
        }
        
        print("🔄 Testing analyze regression with multi=false (this may take 10-45 seconds)...")
        success, data, status = self.make_request('POST', '/closet/analyze', analyze_data, token=self.dev_token, timeout=90)
        
        if success and status == 200:
            # Should have single item analysis
            has_items = 'items' in data and len(data.get('items', [])) == 1
            has_count = data.get('count') == 1
            has_legacy_fields = 'title' in data and 'category' in data
            
            # Check model_used is gemini-*
            model_used = data.get('model_used', '')
            is_gemini_model = model_used.startswith('gemini-')
            
            all_valid = has_items and has_count and has_legacy_fields and is_gemini_model
            self.log_test("Closet Analyze Regression Multi False", all_valid, 
                         f"Items: {len(data.get('items', []))}, Model: {model_used}")
        else:
            self.log_test("Closet Analyze Regression Multi False", False, f"Status: {status}, Data: {data}")

    def test_closet_create_with_clip_embedding(self):
        """NEW: Test POST /api/v1/closet persists clip_embedding and clip_model"""
        if not self.dev_token:
            self.log_test("Closet Create with CLIP Embedding", False, "No dev token available")
            return
            
        test_image_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
        
        item_data = {
            "title": "Test CLIP Embedding Item",
            "category": "Top",
            "image_base64": test_image_b64
        }
        
        print("🔄 Testing closet create with CLIP embedding (this may take 10-30 seconds)...")
        success, data, status = self.make_request('POST', '/closet', item_data, token=self.dev_token, timeout=60)
        
        if success and status == 201:
            item_id = data.get('id')
            
            # Verify via GET /closet/{id} that embedding is persisted
            success2, item_data, status2 = self.make_request('GET', f'/closet/{item_id}', token=self.dev_token)
            
            if success2 and status2 == 200:
                has_clip_embedding = 'clip_embedding' in item_data
                has_clip_model = 'clip_model' in item_data
                
                # Check embedding is 512-d list of floats
                embedding_valid = False
                if has_clip_embedding:
                    embedding = item_data.get('clip_embedding')
                    if isinstance(embedding, list) and len(embedding) == 512:
                        embedding_valid = all(isinstance(x, (int, float)) for x in embedding)
                
                # Check model is patrickjohncyh/fashion-clip
                model_correct = item_data.get('clip_model') == 'patrickjohncyh/fashion-clip'
                
                all_valid = has_clip_embedding and has_clip_model and embedding_valid and model_correct
                self.log_test("Closet Create with CLIP Embedding", all_valid, 
                             f"Embedding: {len(item_data.get('clip_embedding', []))}d, Model: {item_data.get('clip_model')}")
                return item_id
            else:
                self.log_test("Closet Create with CLIP Embedding", False, f"Could not retrieve item: {status2}")
        else:
            self.log_test("Closet Create with CLIP Embedding", False, f"Status: {status}, Data: {data}")
        return None

    def test_closet_list_strips_embedding(self):
        """NEW: Test GET /api/v1/closet strips clip_embedding from list payload"""
        if not self.dev_token:
            self.log_test("Closet List Strips Embedding", False, "No dev token available")
            return
            
        # Test GET /closet (list)
        success, data, status = self.make_request('GET', '/closet', token=self.dev_token)
        
        if success and status == 200:
            items = data.get('items', [])
            if items:
                # Check that no item has clip_embedding in the list response
                no_embeddings = all('clip_embedding' not in item for item in items)
                # But should still have other fields
                has_other_fields = all('title' in item and 'category' in item for item in items)
                
                all_valid = no_embeddings and has_other_fields
                self.log_test("Closet List Strips Embedding", all_valid, 
                             f"Items: {len(items)}, No embeddings: {no_embeddings}")
            else:
                self.log_test("Closet List Strips Embedding", True, "No items found (expected)")
        else:
            self.log_test("Closet List Strips Embedding", False, f"Status: {status}, Data: {data}")

    def test_closet_search_text(self):
        """NEW: Test POST /api/v1/closet/search with text query"""
        if not self.dev_token:
            self.log_test("Closet Search Text", False, "No dev token available")
            return
        
        search_data = {
            "text": "blue shirt casual top",
            "limit": 10,
            "min_score": 0.1
        }
        
        print("🔄 Testing closet search with text (this may take 5-15 seconds)...")
        success, data, status = self.make_request('POST', '/closet/search', search_data, token=self.dev_token, timeout=30)
        
        if success and status == 200:
            # Check response structure
            has_items = 'items' in data and isinstance(data['items'], list)
            has_total = 'total' in data
            has_indexed = 'indexed' in data
            has_model = 'model' in data and data['model'] == 'patrickjohncyh/fashion-clip'
            
            # Check items are sorted by _score DESC and don't include clip_embedding
            items_valid = True
            if data.get('items'):
                prev_score = float('inf')
                for item in data['items']:
                    if '_score' not in item or 'clip_embedding' in item:
                        items_valid = False
                        break
                    if item['_score'] > prev_score:
                        items_valid = False
                        break
                    prev_score = item['_score']
            
            all_valid = has_items and has_total and has_indexed and has_model and items_valid
            self.log_test("Closet Search Text", all_valid, 
                         f"Items: {len(data.get('items', []))}, Total: {data.get('total')}, Indexed: {data.get('indexed')}")
        else:
            self.log_test("Closet Search Text", False, f"Status: {status}, Data: {data}")

    def test_closet_search_auth_validation(self):
        """NEW: Test POST /api/v1/closet/search authentication and validation"""
        # Test without auth - should return 401
        search_data = {"text": "test query"}
        success, data, status = self.make_request('POST', '/closet/search', search_data)
        no_auth_fails = status == 401
        
        # Test missing body fields - should return 400
        if self.dev_token:
            success, data, status = self.make_request('POST', '/closet/search', {}, token=self.dev_token)
            missing_fields_fails = status == 400
        else:
            missing_fields_fails = True
        
        all_validations = no_auth_fails and missing_fields_fails
        self.log_test("Closet Search Auth Validation", all_validations, 
                     f"No auth: 401={no_auth_fails}, Missing fields: 400={missing_fields_fails}")

    def run_all_tests(self):
        """Run all Phase A tests"""
        print("🚀 Starting Phase A Architecture Tests")
        print("=" * 50)
        
        if not self.setup_auth():
            print("❌ Cannot proceed without authentication")
            return False
        
        print("\n📋 Running Phase A Tests...")
        
        # Regression tests
        self.test_closet_analyze_regression_multi_true()
        self.test_closet_analyze_regression_multi_false()
        
        # New features
        item_id = self.test_closet_create_with_clip_embedding()
        self.test_closet_list_strips_embedding()
        self.test_closet_search_text()
        self.test_closet_search_auth_validation()
        
        # Summary
        print("\n" + "=" * 50)
        print(f"📊 Phase A Test Results: {self.tests_passed}/{self.tests_run} passed")
        
        if self.failed_tests:
            print("\n❌ Failed Tests:")
            for test in self.failed_tests:
                print(f"  - {test['test']}: {test['details']}")
        
        return self.tests_passed == self.tests_run

def main():
    tester = PhaseAAPITester()
    success = tester.run_all_tests()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())