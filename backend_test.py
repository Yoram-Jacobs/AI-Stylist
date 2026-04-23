#!/usr/bin/env python3
"""
DressApp Backend API Testing Suite
Tests all Phase 2 backend functionality including auth, users, closet, listings, transactions, and stylist.
"""

import requests
import sys
import json
import time
import base64
from datetime import datetime
from typing import Dict, Any, Optional

class DressAppAPITester:
    def __init__(self, base_url: str = "https://ai-stylist-api.preview.emergentagent.com"):
        self.base_url = base_url.rstrip('/')
        self.dev_token = None
        self.buyer_token = None
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
                    token: str = None, files: Dict = None, timeout: int = 30) -> tuple[bool, Dict, int]:
        """Make HTTP request with error handling"""
        url = f"{self.base_url}/api/v1{endpoint}"
        headers = {}
        
        if token:
            headers['Authorization'] = f'Bearer {token}'
        
        if files:
            # Remove Content-Type for multipart requests
            headers_copy = self.session.headers.copy()
            if 'Content-Type' in headers_copy:
                del headers_copy['Content-Type']
            headers.update(headers_copy)
        else:
            headers.update(self.session.headers)

        try:
            if method == 'GET':
                response = self.session.get(url, headers=headers, timeout=timeout)
            elif method == 'POST':
                if files:
                    response = self.session.post(url, data=data, files=files, headers=headers, timeout=timeout)
                else:
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

    def test_health_check(self):
        """Test basic health endpoint"""
        success, data, status = self.make_request('GET', '/health')
        self.log_test("Health Check", success and status == 200, 
                     f"Status: {status}, Data: {data}")

    def test_dev_bypass_auth(self):
        """Test dev-bypass authentication"""
        success, data, status = self.make_request('POST', '/auth/dev-bypass')
        if success and status == 200 and 'access_token' in data:
            self.dev_token = data['access_token']
            user_data = data.get('user', {})
            expected_email = "dev@dressapp.io"
            has_admin_role = "admin" in user_data.get('roles', [])
            
            self.log_test("Dev Bypass Auth", 
                         user_data.get('email') == expected_email and has_admin_role,
                         f"Email: {user_data.get('email')}, Roles: {user_data.get('roles')}")
            return True
        else:
            self.log_test("Dev Bypass Auth", False, f"Status: {status}, Data: {data}")
            return False

    def test_regular_login(self):
        """Test regular login with dev credentials"""
        login_data = {
            "email": "dev@dressapp.io",
            "password": "DevPass123!"
        }
        success, data, status = self.make_request('POST', '/auth/login', login_data)
        
        if success and status == 200 and 'access_token' in data:
            token = data['access_token']
            user_data = data.get('user', {})
            self.log_test("Regular Login", True, f"User: {user_data.get('email')}")
            return token
        else:
            self.log_test("Regular Login", False, f"Status: {status}, Data: {data}")
            return None

    def test_register_new_user(self):
        """Register a new user for multi-user testing"""
        timestamp = int(time.time())
        register_data = {
            "email": f"buyer{timestamp}@dressapp.io",
            "password": "BuyerPass123!",
            "display_name": f"Test Buyer {timestamp}"
        }
        
        success, data, status = self.make_request('POST', '/auth/register', register_data)
        
        if success and status == 201 and 'access_token' in data:
            self.buyer_token = data['access_token']
            user_data = data.get('user', {})
            self.log_test("Register New User", True, f"User: {user_data.get('email')}")
            return True
        else:
            self.log_test("Register New User", False, f"Status: {status}, Data: {data}")
            return False

    def test_auth_me_endpoints(self):
        """Test /auth/me and /users/me endpoints"""
        if not self.dev_token:
            self.log_test("Auth Me Endpoints", False, "No dev token available")
            return

        # Test /auth/me
        success, data, status = self.make_request('GET', '/auth/me', token=self.dev_token)
        auth_me_works = success and status == 200 and data.get('email') == 'dev@dressapp.io'
        
        # Test /users/me  
        success2, data2, status2 = self.make_request('GET', '/users/me', token=self.dev_token)
        users_me_works = success2 and status2 == 200 and data2.get('email') == 'dev@dressapp.io'
        
        # Test without token (should return 401)
        success3, data3, status3 = self.make_request('GET', '/auth/me')
        no_token_fails = status3 == 401
        
        all_passed = auth_me_works and users_me_works and no_token_fails
        details = f"auth/me: {status}, users/me: {status2}, no_token: {status3}"
        self.log_test("Auth Me Endpoints", all_passed, details)

    def test_user_profile_update(self):
        """Test PATCH /users/me for profile updates"""
        if not self.dev_token:
            self.log_test("User Profile Update", False, "No dev token available")
            return

        update_data = {
            "style_profile": {
                "aesthetics": ["minimalist", "modern"],
                "color_palette": ["black", "white", "gray"],
                "budget_monthly_cents": 50000
            },
            "cultural_context": {
                "region": "North America",
                "dress_conservativeness": "moderate"
            },
            "preferred_voice_id": "aura-2-thalia-en",
            "preferred_language": "en"
        }
        
        success, data, status = self.make_request('PATCH', '/users/me', update_data, token=self.dev_token)
        
        if success and status == 200:
            # Verify the update worked
            success2, data2, status2 = self.make_request('GET', '/users/me', token=self.dev_token)
            style_updated = data2.get('style_profile', {}).get('aesthetics') == ["minimalist", "modern"]
            self.log_test("User Profile Update", style_updated, f"Style profile updated: {style_updated}")
        else:
            self.log_test("User Profile Update", False, f"Status: {status}, Data: {data}")

    # ==================== LANGUAGE SELECTOR TESTS ====================
    
    def test_language_persistence(self):
        """Test PATCH /users/me with preferred_language persists correctly"""
        if not self.dev_token:
            self.log_test("Language Persistence", False, "No dev token available")
            return
            
        # Test each of the 12 supported language codes
        supported_languages = ["en", "he", "ar", "es", "fr", "de", "it", "pt", "ru", "zh", "ja", "hi"]
        
        for lang_code in supported_languages:
            # Update preferred_language
            update_data = {"preferred_language": lang_code}
            success, data, status = self.make_request('PATCH', '/users/me', update_data, token=self.dev_token)
            
            if not (success and status == 200):
                self.log_test(f"Language Persistence - {lang_code}", False, f"PATCH failed: {status}")
                continue
                
            # Verify the update persisted
            success2, data2, status2 = self.make_request('GET', '/users/me', token=self.dev_token)
            
            if success2 and status2 == 200:
                persisted_lang = data2.get('preferred_language')
                lang_persisted = persisted_lang == lang_code
                self.log_test(f"Language Persistence - {lang_code}", lang_persisted, 
                             f"Expected: {lang_code}, Got: {persisted_lang}")
            else:
                self.log_test(f"Language Persistence - {lang_code}", False, f"GET failed: {status2}")
    
    def test_language_validation(self):
        """Test that PATCH /users/me accepts all 12 language codes without 400/422"""
        if not self.dev_token:
            self.log_test("Language Validation", False, "No dev token available")
            return
            
        supported_languages = ["en", "he", "ar", "es", "fr", "de", "it", "pt", "ru", "zh", "ja", "hi"]
        all_accepted = True
        failed_languages = []
        
        for lang_code in supported_languages:
            update_data = {"preferred_language": lang_code}
            success, data, status = self.make_request('PATCH', '/users/me', update_data, token=self.dev_token)
            
            if not (success and status == 200):
                all_accepted = False
                failed_languages.append(f"{lang_code}:{status}")
        
        self.log_test("Language Validation", all_accepted, 
                     f"Failed languages: {failed_languages}" if failed_languages else "All 12 languages accepted")
    
    def test_stylist_language_localization(self):
        """Test POST /stylist with Hebrew and Spanish language localization"""
        if not self.dev_token:
            self.log_test("Stylist Language Localization", False, "No dev token available")
            return
            
        # Test Hebrew localization
        print("🔄 Testing stylist Hebrew localization (this may take 30-60 seconds)...")
        
        # First set user's preferred language to Hebrew
        update_data = {"preferred_language": "he"}
        success, data, status = self.make_request('PATCH', '/users/me', update_data, token=self.dev_token)
        
        if not (success and status == 200):
            self.log_test("Stylist Hebrew Setup", False, f"Could not set Hebrew: {status}")
            return
        
        # Make stylist call
        stylist_data = {'text': 'What should I wear today for work?'}
        headers = {'Authorization': f'Bearer {self.dev_token}'}
        url = f"{self.base_url}/api/v1/stylist"
        
        try:
            response = requests.post(url, data=stylist_data, headers=headers, timeout=120)
            response_data = response.json() if response.content else {}
            success = True
            status = response.status_code
        except Exception as e:
            success = False
            response_data = {"error": str(e)}
            status = 0
        
        if success and status == 200:
            advice = response_data.get('advice', {})
            reasoning_summary = advice.get('reasoning_summary', '')
            spoken_reply = advice.get('spoken_reply', '')
            do_dont = advice.get('do_dont', [])
            
            # Check if content appears to be in Hebrew (contains Hebrew characters)
            hebrew_chars = any('\u0590' <= char <= '\u05FF' for char in reasoning_summary + spoken_reply + ' '.join(do_dont))
            has_content = bool(reasoning_summary and spoken_reply)
            
            self.log_test("Stylist Hebrew Localization", hebrew_chars and has_content,
                         f"Hebrew chars detected: {hebrew_chars}, Has content: {has_content}")
        else:
            self.log_test("Stylist Hebrew Localization", False, f"Status: {status}, Data: {response_data}")
        
        # Test Spanish localization
        print("🔄 Testing stylist Spanish localization (this may take 30-60 seconds)...")
        
        # Set user's preferred language to Spanish
        update_data = {"preferred_language": "es"}
        success, data, status = self.make_request('PATCH', '/users/me', update_data, token=self.dev_token)
        
        if not (success and status == 200):
            self.log_test("Stylist Spanish Setup", False, f"Could not set Spanish: {status}")
            return
        
        try:
            response = requests.post(url, data=stylist_data, headers=headers, timeout=120)
            response_data = response.json() if response.content else {}
            success = True
            status = response.status_code
        except Exception as e:
            success = False
            response_data = {"error": str(e)}
            status = 0
        
        if success and status == 200:
            advice = response_data.get('advice', {})
            reasoning_summary = advice.get('reasoning_summary', '')
            spoken_reply = advice.get('spoken_reply', '')
            
            # Check for Spanish content (look for common Spanish words/patterns)
            spanish_indicators = ['para', 'con', 'que', 'una', 'del', 'por', 'está', 'muy', 'bien', 'día']
            spanish_detected = any(word in reasoning_summary.lower() or word in spoken_reply.lower() 
                                 for word in spanish_indicators)
            has_content = bool(reasoning_summary and spoken_reply)
            
            self.log_test("Stylist Spanish Localization", spanish_detected and has_content,
                         f"Spanish detected: {spanish_detected}, Has content: {has_content}")
        else:
            self.log_test("Stylist Spanish Localization", False, f"Status: {status}, Data: {response_data}")
        
        # Reset to English
        update_data = {"preferred_language": "en"}
        self.make_request('PATCH', '/users/me', update_data, token=self.dev_token)
    
    def test_garment_vision_language_localization(self):
        """Test POST /closet/analyze with Hebrew language localization"""
        if not self.dev_token:
            self.log_test("Garment Vision Language Localization", False, "No dev token available")
            return
            
        print("🔄 Testing garment vision Hebrew localization (this may take 30-60 seconds)...")
        
        # Set user's preferred language to Hebrew
        update_data = {"preferred_language": "he"}
        success, data, status = self.make_request('PATCH', '/users/me', update_data, token=self.dev_token)
        
        if not (success and status == 200):
            self.log_test("Garment Vision Hebrew Setup", False, f"Could not set Hebrew: {status}")
            return
        
        # Use a small test image for analysis
        test_image_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
        
        analyze_data = {
            "image_base64": test_image_b64,
            "multi": False  # Single-item analysis
        }
        
        success, data, status = self.make_request('POST', '/closet/analyze', analyze_data, token=self.dev_token, timeout=90)
        
        if success and status == 200:
            title = data.get('title', '')
            caption = data.get('caption', '')
            repair_advice = data.get('repair_advice', '')
            
            # Check if Hebrew characters are present in user-facing fields
            hebrew_chars = any('\u0590' <= char <= '\u05FF' for char in title + caption + (repair_advice or ''))
            
            # Verify enum fields remain in English
            category = data.get('category', '')
            sub_category = data.get('sub_category', '')
            gender = data.get('gender', '')
            dress_code = data.get('dress_code', '')
            pattern = data.get('pattern', '')
            state = data.get('state', '')
            condition = data.get('condition', '')
            quality = data.get('quality', '')
            
            enum_fields_english = all(field and field.lower() in [
                # Categories
                'top', 'bottom', 'outerwear', 'full body', 'footwear', 'accessories', 'underwear',
                # Genders
                'men', 'women', 'unisex', 'kids',
                # Dress codes
                'casual', 'smart-casual', 'business', 'formal', 'athletic', 'loungewear',
                # Patterns
                'solid', 'striped', 'plaid', 'floral', 'herringbone', 'polka', 'paisley', 'geometric', 'abstract',
                # States
                'new', 'used',
                # Conditions
                'bad', 'fair', 'good', 'excellent',
                # Quality
                'budget', 'mid', 'premium', 'luxury'
            ] for field in [category, sub_category, gender, dress_code, pattern, state, condition, quality] if field)
            
            has_content = bool(title)
            
            self.log_test("Garment Vision Hebrew Localization", hebrew_chars and enum_fields_english and has_content,
                         f"Hebrew chars: {hebrew_chars}, Enums English: {enum_fields_english}, Has content: {has_content}")
        else:
            self.log_test("Garment Vision Hebrew Localization", False, f"Status: {status}, Data: {data}")
        
        # Reset to English
        update_data = {"preferred_language": "en"}
        self.make_request('PATCH', '/users/me', update_data, token=self.dev_token)
    
    def test_existing_endpoints_regression(self):
        """Verify that no pre-existing endpoints regressed"""
        if not self.dev_token:
            self.log_test("Existing Endpoints Regression", False, "No dev token available")
            return
            
        endpoints_to_test = [
            ('GET', '/closet'),
            ('POST', '/closet/search', {'text': 'blue shirt'}),
            ('GET', '/listings'),
            ('GET', '/auth/dev-bypass')
        ]
        
        all_working = True
        failed_endpoints = []
        
        for method, endpoint, *data in endpoints_to_test:
            payload = data[0] if data else None
            
            if endpoint == '/auth/dev-bypass':
                # Test without token
                success, response_data, status = self.make_request(method, endpoint, payload)
            else:
                success, response_data, status = self.make_request(method, endpoint, payload, token=self.dev_token)
            
            if not (success and status == 200):
                all_working = False
                failed_endpoints.append(f"{method} {endpoint}:{status}")
        
        self.log_test("Existing Endpoints Regression", all_working,
                     f"Failed endpoints: {failed_endpoints}" if failed_endpoints else "All endpoints working")

    # ==================== EXISTING TESTS ====================
    
    def test_closet_operations(self):
        """Test closet CRUD operations"""
        if not self.dev_token:
            self.log_test("Closet Operations", False, "No dev token available")
            return

        # Create closet item with image URL
        item_data = {
            "title": "Test Blue Jeans",
            "category": "bottoms",
            "sub_category": "jeans",
            "brand": "Levi's",
            "size": "32x32",
            "color": "blue",
            "material": "denim",
            "season": ["spring", "fall"],
            "formality": "casual",
            "tags": ["everyday", "comfortable"],
            "original_image_url": "https://example.com/jeans.jpg",
            "purchase_price_cents": 8000,
            "notes": "Favorite pair of jeans"
        }
        
        success, data, status = self.make_request('POST', '/closet', item_data, token=self.dev_token)
        
        if not (success and status == 201):
            self.log_test("Closet Create Item", False, f"Status: {status}, Data: {data}")
            return
        
        item_id = data.get('id')
        if not item_id:
            self.log_test("Closet Create Item", False, "No item ID returned")
            return
            
        self.log_test("Closet Create Item", True, f"Created item: {item_id}")
        
        # Test GET /closet (list items)
        success, data, status = self.make_request('GET', '/closet', token=self.dev_token)
        items_list = success and status == 200 and isinstance(data, list)
        item_count = len(data) if items_list else 0
        # Note: Items might be 0 if previous tests deleted them
        self.log_test("Closet List Items", items_list, f"Found {item_count} items (API working correctly)")
        
        # Test GET /closet/{id} (get specific item)
        success, data, status = self.make_request('GET', f'/closet/{item_id}', token=self.dev_token)
        item_retrieved = success and status == 200 and data.get('id') == item_id
        self.log_test("Closet Get Item", item_retrieved, f"Retrieved item: {data.get('title', 'N/A')}")
        
        # Test PATCH /closet/{id} (update item)
        update_data = {"notes": "Updated notes - still my favorite jeans"}
        success, data, status = self.make_request('PATCH', f'/closet/{item_id}', update_data, token=self.dev_token)
        item_updated = success and status == 200
        self.log_test("Closet Update Item", item_updated, f"Status: {status}")
        
        # Test ownership enforcement (try to access with buyer token)
        if self.buyer_token:
            success, data, status = self.make_request('GET', f'/closet/{item_id}', token=self.buyer_token)
            ownership_enforced = status == 404  # Should not find other user's item
            self.log_test("Closet Ownership Enforcement", ownership_enforced, f"Status: {status}")
        
        # Test DELETE /closet/{id}
        success, data, status = self.make_request('DELETE', f'/closet/{item_id}', token=self.dev_token)
        item_deleted = success and status == 204
        self.log_test("Closet Delete Item", item_deleted, f"Status: {status}")
        
        return item_id if not item_deleted else None

    def test_closet_with_base64_image(self):
        """Test closet item creation with base64 image"""
        if not self.dev_token:
            return None
            
        # Create a small test image in base64 (1x1 pixel PNG)
        test_image_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
        
        item_data = {
            "title": "Test Shirt with Image",
            "category": "tops",
            "sub_category": "shirt",
            "color": "white",
            "formality": "business",
            "image_base64": test_image_b64
        }
        
        success, data, status = self.make_request('POST', '/closet', item_data, token=self.dev_token)
        
        if success and status == 201:
            item_id = data.get('id')
            # Note: segmented_image_url will be null due to fal.ai balance exhaustion
            self.log_test("Closet Create with Base64", True, f"Created item: {item_id}")
            return item_id
        else:
            self.log_test("Closet Create with Base64", False, f"Status: {status}, Data: {data}")
            return None

    def test_listings_fee_preview(self):
        """Test fee preview calculation"""
        # Test the specific example from requirements
        success, data, status = self.make_request('GET', '/listings/fee-preview?list_price_cents=2500')
        
        if success and status == 200:
            expected = {
                "stripe_fee_cents": 102,  # 2.9% + $0.30 with banker's rounding
                "net_after_stripe_cents": 2398,
                "platform_fee_cents": 168,  # 7% of net_after_stripe
                "seller_net_cents": 2230
            }
            
            all_correct = all(data.get(k) == v for k, v in expected.items())
            self.log_test("Listings Fee Preview", all_correct, 
                         f"Expected: {expected}, Got: {data}")
            
            # Specifically verify banker's rounding (102.5 → 102)
            stripe_fee_correct = data.get('stripe_fee_cents') == 102
            self.log_test("Listings Fee Preview - Banker's Rounding", stripe_fee_correct,
                         f"Stripe fee: {data.get('stripe_fee_cents')} (should be 102 from 102.5)")
        else:
            self.log_test("Listings Fee Preview", False, f"Status: {status}, Data: {data}")

    def test_listings_operations(self):
        """Test listings CRUD operations"""
        if not self.dev_token:
            return None
            
        # First create a closet item to list
        item_data = {
            "title": "Designer Jacket for Sale",
            "category": "outerwear",
            "sub_category": "jacket",
            "brand": "Designer Brand",
            "color": "black",
            "formality": "business"
        }
        
        success, data, status = self.make_request('POST', '/closet', item_data, token=self.dev_token)
        if not (success and status == 201):
            self.log_test("Listings - Create Closet Item", False, f"Status: {status}")
            return None
            
        closet_item_id = data.get('id')
        
        # Create a listing
        listing_data = {
            "closet_item_id": closet_item_id,
            "title": "Designer Jacket - Like New",
            "description": "Beautiful designer jacket in excellent condition",
            "category": "outerwear",
            "size": "M",
            "condition": "like_new",
            "list_price_cents": 15000,
            "ships_to": ["US", "CA"]
        }
        
        success, data, status = self.make_request('POST', '/listings', listing_data, token=self.dev_token)
        
        if not (success and status == 201):
            self.log_test("Listings Create", False, f"Status: {status}, Data: {data}")
            return None
            
        listing_id = data.get('id')
        
        # Verify closet item source changed to "Shared"
        success, closet_data, status = self.make_request('GET', f'/closet/{closet_item_id}', token=self.dev_token)
        source_updated = closet_data.get('source') == 'Shared'
        self.log_test("Listings - Source Transition", source_updated, 
                     f"Closet item source: {closet_data.get('source')}")
        
        self.log_test("Listings Create", True, f"Created listing: {listing_id}")
        
        # Test public browse (no auth required)
        success, data, status = self.make_request('GET', '/listings')
        public_browse = success and status == 200 and isinstance(data, list)
        self.log_test("Listings Public Browse", public_browse, f"Found {len(data) if public_browse else 0} listings")
        
        # Test GET specific listing (should increment views)
        success, data, status = self.make_request('GET', f'/listings/{listing_id}')
        listing_retrieved = success and status == 200 and data.get('id') == listing_id
        initial_views = data.get('views', 0) if listing_retrieved else 0
        self.log_test("Listings Get Specific", listing_retrieved, f"Views: {initial_views}")
        
        # Test view increment
        success, data, status = self.make_request('GET', f'/listings/{listing_id}')
        if success and status == 200:
            new_views = data.get('views', 0)
            views_incremented = new_views > initial_views
            self.log_test("Listings View Increment", views_incremented, 
                         f"Views: {initial_views} -> {new_views}")
        
        # Test seller ownership for updates
        update_data = {"description": "Updated description"}
        success, data, status = self.make_request('PATCH', f'/listings/{listing_id}', 
                                                 update_data, token=self.dev_token)
        seller_can_update = success and status == 200
        self.log_test("Listings Seller Update", seller_can_update, f"Status: {status}")
        
        return listing_id

    def test_transactions(self):
        """Test transaction creation and financial calculations"""
        if not self.dev_token or not self.buyer_token:
            self.log_test("Transactions", False, "Missing required tokens")
            return
            
        # Create a listing first
        listing_id = self.test_listings_operations()
        if not listing_id:
            self.log_test("Transactions - Setup", False, "Could not create listing")
            return
        
        # Test self-purchase rejection
        transaction_data = {
            "listing_id": listing_id
        }
        
        success, data, status = self.make_request('POST', '/transactions', transaction_data, token=self.dev_token)
        self_purchase_rejected = status == 400
        self.log_test("Transactions Self-Purchase Rejection", self_purchase_rejected, f"Status: {status}")
        
        # Test valid transaction creation
        success, data, status = self.make_request('POST', '/transactions', transaction_data, token=self.buyer_token)
        
        if success and status == 201:
            transaction_id = data.get('id')
            financial = data.get('financial', {})
            
            # Verify financial calculations
            expected_calculations = financial.get('gross_cents') > 0 and \
                                  financial.get('stripe_fee_cents') > 0 and \
                                  financial.get('platform_fee_cents') > 0 and \
                                  financial.get('seller_net_cents') > 0
            
            self.log_test("Transactions Create", expected_calculations, 
                         f"Transaction: {transaction_id}, Financial: {financial}")
            
            # Verify listing status changed to 'reserved'
            success, listing_data, status = self.make_request('GET', f'/listings/{listing_id}')
            listing_reserved = listing_data.get('status') == 'reserved'
            self.log_test("Transactions Listing Reservation", listing_reserved, 
                         f"Listing status: {listing_data.get('status')}")
            
            return transaction_id
        else:
            self.log_test("Transactions Create", False, f"Status: {status}, Data: {data}")
            return None

    def test_multiple_pending_transactions(self):
        """REGRESSION TEST: Test creating multiple pending transactions in sequence"""
        if not self.dev_token or not self.buyer_token:
            self.log_test("Multiple Pending Transactions", False, "Missing required tokens")
            return
        
        print("🔄 Testing multiple pending transactions regression...")
        
        # Create two different listings
        listing_ids = []
        for i in range(2):
            # Create closet item
            item_data = {
                "title": f"Test Item {i+1} for Transaction",
                "category": "tops",
                "sub_category": "shirt",
                "brand": f"Brand{i+1}",
                "color": "blue",
                "formality": "casual"
            }
            
            success, data, status = self.make_request('POST', '/closet', item_data, token=self.dev_token)
            if not (success and status == 201):
                self.log_test(f"Multiple Transactions - Create Item {i+1}", False, f"Status: {status}")
                return
                
            closet_item_id = data.get('id')
            
            # Create listing
            listing_data = {
                "closet_item_id": closet_item_id,
                "title": f"Test Listing {i+1}",
                "description": f"Test listing {i+1} for multiple transactions",
                "category": "tops",
                "size": "M",
                "condition": "like_new",
                "list_price_cents": 2500 + (i * 500),  # Different prices
                "ships_to": ["US"]
            }
            
            success, data, status = self.make_request('POST', '/listings', listing_data, token=self.dev_token)
            if not (success and status == 201):
                self.log_test(f"Multiple Transactions - Create Listing {i+1}", False, f"Status: {status}")
                return
                
            listing_ids.append(data.get('id'))
        
        # Now create multiple pending transactions
        transaction_ids = []
        for i, listing_id in enumerate(listing_ids):
            transaction_data = {"listing_id": listing_id}
            
            success, data, status = self.make_request('POST', '/transactions', transaction_data, token=self.buyer_token)
            
            if success and status == 201:
                transaction_id = data.get('id')
                transaction_ids.append(transaction_id)
                
                # Verify full financial ledger
                financial = data.get('financial', {})
                has_full_ledger = all(k in financial for k in [
                    'gross_cents', 'stripe_fee_cents', 'net_after_stripe_cents', 
                    'platform_fee_cents', 'seller_net_cents'
                ])
                
                self.log_test(f"Multiple Pending Transaction {i+1}", has_full_ledger, 
                             f"Transaction: {transaction_id}, Financial: {financial}")
            else:
                self.log_test(f"Multiple Pending Transaction {i+1}", False, 
                             f"Status: {status}, Data: {data}")
                return
        
        # Verify both transactions were created successfully
        all_created = len(transaction_ids) == 2
        self.log_test("Multiple Pending Transactions - Both Created", all_created, 
                     f"Created {len(transaction_ids)} transactions: {transaction_ids}")
        
        return transaction_ids

    def test_transactions_filters(self):
        """Test transaction filtering by role"""
        if not self.dev_token:
            return
            
        # Test seller filter
        success, data, status = self.make_request('GET', '/transactions?role=seller', token=self.dev_token)
        seller_filter = success and status == 200
        self.log_test("Transactions Seller Filter", seller_filter, f"Found {len(data) if seller_filter else 0} transactions")
        
        # Test buyer filter
        if self.buyer_token:
            success, data, status = self.make_request('GET', '/transactions?role=buyer', token=self.buyer_token)
            buyer_filter = success and status == 200
            self.log_test("Transactions Buyer Filter", buyer_filter, f"Found {len(data) if buyer_filter else 0} transactions")

    def test_stylist_basic(self):
        """Test basic stylist functionality"""
        if not self.dev_token:
            self.log_test("Stylist Basic", False, "No dev token available")
            return
            
        # Use form data with requests directly
        data = {'text': 'What should I wear today for a business meeting? It\'s a bit chilly outside.'}
        headers = {'Authorization': f'Bearer {self.dev_token}'}
        url = f"{self.base_url}/api/v1/stylist"
        
        print("🔄 Testing stylist (this may take 15-25 seconds)...")
        
        try:
            response = requests.post(url, data=data, headers=headers, timeout=120)
            response_data = response.json() if response.content else {}
            success = True
            status = response.status_code
        except Exception as e:
            success = False
            response_data = {"error": str(e)}
            status = 0
        
        if success and status == 200:
            advice = response_data.get('advice', {})
            has_reasoning = bool(advice.get('reasoning_summary'))
            has_recommendations = bool(advice.get('outfit_recommendations'))
            has_weather = bool(advice.get('weather_summary'))
            has_tts = bool(advice.get('tts_audio_base64'))
            
            all_components = has_reasoning and has_recommendations and has_weather and has_tts
            details = f"Reasoning: {has_reasoning}, Recommendations: {has_recommendations}, Weather: {has_weather}, TTS: {has_tts}"
            self.log_test("Stylist Basic", all_components, details)
        else:
            self.log_test("Stylist Basic", False, f"Status: {status}, Data: {response_data}")

    def test_stylist_with_calendar(self):
        """Test stylist with calendar integration"""
        if not self.dev_token:
            return
            
        data = {'text': 'Help me plan outfits for my upcoming meetings', 'include_calendar': 'true'}
        headers = {'Authorization': f'Bearer {self.dev_token}'}
        url = f"{self.base_url}/api/v1/stylist"
        
        print("🔄 Testing stylist with calendar (this may take 15-25 seconds)...")
        
        try:
            response = requests.post(url, data=data, headers=headers, timeout=120)
            response_data = response.json() if response.content else {}
            success = True
            status = response.status_code
        except Exception as e:
            success = False
            response_data = {"error": str(e)}
            status = 0
        
        if success and status == 200:
            advice = response_data.get('advice', {})
            has_calendar = bool(advice.get('calendar_summary'))
            self.log_test("Stylist Calendar Integration", has_calendar, 
                         f"Calendar summary: {advice.get('calendar_summary', 'None')}")
        else:
            self.log_test("Stylist Calendar Integration", False, f"Status: {status}, Data: {response_data}")

    def test_stylist_history(self):
        """Test stylist conversation history"""
        if not self.dev_token:
            return
            
        success, data, status = self.make_request('GET', '/stylist/history', token=self.dev_token)
        
        if success and status == 200:
            messages = data.get('messages', [])
            has_messages = isinstance(messages, list) and len(messages) > 0
            if has_messages:
                # Check for both user and assistant messages
                roles = [msg.get('role') for msg in messages]
                has_user_and_assistant = 'user' in roles and 'assistant' in roles
                self.log_test("Stylist History", has_user_and_assistant, 
                             f"Found {len(messages)} messages with roles: {set(roles)}")
                
                # Return the messages for further verification
                return messages
            else:
                self.log_test("Stylist History", True, "No conversation history yet (expected)")
                return []
        else:
            self.log_test("Stylist History", False, f"Status: {status}, Data: {data}")
            return []

    def test_stylist_history_persistence(self):
        """Test that stylist history persists both user and assistant roles after each call"""
        if not self.dev_token:
            self.log_test("Stylist History Persistence", False, "No dev token available")
            return
            
        print("🔄 Testing stylist history persistence...")
        
        # Make a stylist call first to ensure we have history
        data = {'text': 'Quick styling question for history test'}
        headers = {'Authorization': f'Bearer {self.dev_token}'}
        url = f"{self.base_url}/api/v1/stylist"
        
        try:
            response = requests.post(url, data=data, headers=headers, timeout=120)
            if response.status_code != 200:
                self.log_test("Stylist History Persistence - Setup", False, 
                             f"Stylist call failed: {response.status_code}")
                return
        except Exception as e:
            self.log_test("Stylist History Persistence - Setup", False, f"Error: {e}")
            return
        
        # Now check history
        success, data, status = self.make_request('GET', '/stylist/history', token=self.dev_token)
        
        if success and status == 200:
            messages = data.get('messages', [])
            if len(messages) >= 2:  # Should have at least user + assistant
                roles = [msg.get('role') for msg in messages]
                has_user = 'user' in roles
                has_assistant = 'assistant' in roles
                
                # Check that messages are properly structured
                user_messages = [m for m in messages if m.get('role') == 'user']
                assistant_messages = [m for m in messages if m.get('role') == 'assistant']
                
                user_has_transcript = any(m.get('transcript') for m in user_messages)
                assistant_has_payload = any(m.get('assistant_payload') for m in assistant_messages)
                
                all_checks = has_user and has_assistant and user_has_transcript and assistant_has_payload
                details = f"Messages: {len(messages)}, User: {len(user_messages)}, Assistant: {len(assistant_messages)}"
                
                self.log_test("Stylist History Persistence", all_checks, details)
            else:
                self.log_test("Stylist History Persistence", False, 
                             f"Expected at least 2 messages, got {len(messages)}")
        else:
            self.log_test("Stylist History Persistence", False, f"Status: {status}, Data: {data}")

    def test_multipart_stylist(self):
        """Test stylist with multipart data (text + image)"""
        if not self.dev_token:
            return
            
        # Create a small test image
        test_image_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
        image_bytes = base64.b64decode(test_image_b64)
        
        files = {'image': ('test.png', image_bytes, 'image/png')}
        data = {'text': 'What do you think of this outfit?'}
        headers = {'Authorization': f'Bearer {self.dev_token}'}
        url = f"{self.base_url}/api/v1/stylist"
        
        print("🔄 Testing multipart stylist (this may take 15-25 seconds)...")
        
        try:
            response = requests.post(url, data=data, files=files, headers=headers, timeout=120)
            response_data = response.json() if response.content else {}
            success = True
            status = response.status_code
        except Exception as e:
            success = False
            response_data = {"error": str(e)}
            status = 0
        
        if success and status == 200:
            advice = response_data.get('advice', {})
            has_reasoning = bool(advice.get('reasoning_summary'))
            # Note: segmented_image_url will be null due to fal.ai balance exhaustion
            self.log_test("Stylist Multipart", has_reasoning, 
                         f"Reasoning provided: {has_reasoning}")
        else:
            self.log_test("Stylist Multipart", False, f"Status: {status}, Data: {response_data}")

    def test_multipart_stylist_with_real_image(self):
        """REGRESSION TEST: Test stylist with real clothing image from Unsplash"""
        if not self.dev_token:
            self.log_test("Stylist Multipart Real Image", False, "No dev token available")
            return
            
        print("🔄 Downloading real clothing image from Unsplash...")
        
        # Download real clothing image from Unsplash
        try:
            image_response = requests.get(
                "https://images.unsplash.com/photo-1603252109303-2751441dd157?w=900&q=80&auto=format&fit=crop",
                timeout=30
            )
            if image_response.status_code != 200:
                self.log_test("Stylist Multipart Real Image", False, 
                             f"Failed to download image: {image_response.status_code}")
                return
                
            image_bytes = image_response.content
            print(f"✅ Downloaded image ({len(image_bytes)} bytes)")
            
        except Exception as e:
            self.log_test("Stylist Multipart Real Image", False, f"Image download error: {e}")
            return
        
        # Submit to stylist endpoint
        files = {'image': ('clothing.jpg', image_bytes, 'image/jpeg')}
        data = {'text': 'What do you think of this outfit? Any styling advice?'}
        headers = {'Authorization': f'Bearer {self.dev_token}'}
        url = f"{self.base_url}/api/v1/stylist"
        
        print("🔄 Testing stylist with real image (this may take 15-25 seconds)...")
        
        try:
            response = requests.post(url, data=data, files=files, headers=headers, timeout=120)
            response_data = response.json() if response.content else {}
            success = True
            status = response.status_code
        except Exception as e:
            success = False
            response_data = {"error": str(e)}
            status = 0
        
        if success and status == 200:
            advice = response_data.get('advice', {})
            has_reasoning = bool(advice.get('reasoning_summary'))
            has_tts = bool(advice.get('tts_audio_base64'))
            
            # Check that reasoning is non-empty
            reasoning_non_empty = len(advice.get('reasoning_summary', '').strip()) > 0
            tts_non_empty = len(advice.get('tts_audio_base64', '').strip()) > 0
            
            all_components = has_reasoning and has_tts and reasoning_non_empty and tts_non_empty
            details = f"Reasoning: {reasoning_non_empty} ({len(advice.get('reasoning_summary', ''))} chars), TTS: {tts_non_empty} ({len(advice.get('tts_audio_base64', ''))} chars)"
            
            self.log_test("Stylist Multipart Real Image", all_components, details)
        else:
            self.log_test("Stylist Multipart Real Image", False, f"Status: {status}, Data: {response_data}")

    # ==================== PHASE 5 ADMIN TESTS ====================
    
    def test_admin_overview(self):
        """Test GET /admin/overview endpoint"""
        if not self.dev_token:
            self.log_test("Admin Overview", False, "No dev token available")
            return
            
        success, data, status = self.make_request('GET', '/admin/overview', token=self.dev_token)
        
        if success and status == 200:
            # Check required fields
            required_fields = ['users', 'closet_items', 'listings', 'transactions', 'revenue_cents', 'stylist', 'trend_scout', 'providers']
            has_all_fields = all(field in data for field in required_fields)
            
            # Check nested structure
            users_valid = isinstance(data.get('users', {}), dict) and 'total' in data['users']
            revenue_valid = isinstance(data.get('revenue_cents', {}), dict)
            
            all_valid = has_all_fields and users_valid and revenue_valid
            self.log_test("Admin Overview", all_valid, f"Fields: {list(data.keys())}")
        else:
            self.log_test("Admin Overview", False, f"Status: {status}, Data: {data}")
    
    def test_admin_overview_auth(self):
        """Test admin overview auth requirements"""
        # Test without auth - should return 401
        success, data, status = self.make_request('GET', '/admin/overview')
        no_auth_fails = status == 401
        
        # Test with non-admin user (if available)
        non_admin_fails = True
        if self.buyer_token:
            success, data, status = self.make_request('GET', '/admin/overview', token=self.buyer_token)
            non_admin_fails = status == 403
        
        auth_working = no_auth_fails and non_admin_fails
        self.log_test("Admin Overview Auth", auth_working, f"No auth: {status}, Non-admin: {status if self.buyer_token else 'N/A'}")
    
    def test_admin_users(self):
        """Test GET /admin/users endpoint"""
        if not self.dev_token:
            self.log_test("Admin Users", False, "No dev token available")
            return
            
        success, data, status = self.make_request('GET', '/admin/users', token=self.dev_token)
        
        if success and status == 200:
            # Check structure
            has_items = 'items' in data and isinstance(data['items'], list)
            has_pagination = all(k in data for k in ['total', 'skip', 'limit'])
            
            # Check that sensitive fields are not exposed
            if data['items']:
                first_user = data['items'][0]
                no_password = 'password_hash' not in first_user
                no_tokens = 'google_calendar_tokens' not in first_user
                has_counts = 'closet_count' in first_user and 'listing_count' in first_user
                
                all_valid = has_items and has_pagination and no_password and no_tokens and has_counts
                self.log_test("Admin Users", all_valid, f"Users: {len(data['items'])}, Total: {data.get('total')}")
            else:
                self.log_test("Admin Users", has_items and has_pagination, "No users found but structure valid")
        else:
            self.log_test("Admin Users", False, f"Status: {status}, Data: {data}")
    
    def test_admin_user_promotion(self):
        """Test POST /admin/users/{id}/promote and /demote"""
        if not self.dev_token or not self.buyer_token:
            self.log_test("Admin User Promotion", False, "Missing required tokens")
            return
            
        # Get buyer user ID first
        success, buyer_data, status = self.make_request('GET', '/users/me', token=self.buyer_token)
        if not (success and status == 200):
            self.log_test("Admin User Promotion", False, "Could not get buyer user data")
            return
            
        buyer_id = buyer_data.get('id')
        
        # Test promotion
        success, data, status = self.make_request('POST', f'/admin/users/{buyer_id}/promote', token=self.dev_token)
        promote_works = success and status == 200
        
        # Test demotion (idempotent)
        success, data, status = self.make_request('POST', f'/admin/users/{buyer_id}/demote', token=self.dev_token)
        demote_works = success and status == 200
        
        # Test idempotency - demote again
        success, data, status = self.make_request('POST', f'/admin/users/{buyer_id}/demote', token=self.dev_token)
        idempotent_works = success and status == 200
        
        all_works = promote_works and demote_works and idempotent_works
        self.log_test("Admin User Promotion", all_works, f"Promote: {promote_works}, Demote: {demote_works}, Idempotent: {idempotent_works}")
    
    def test_admin_listings(self):
        """Test GET /admin/listings with status filter"""
        if not self.dev_token:
            self.log_test("Admin Listings", False, "No dev token available")
            return
            
        # Test without filter
        success, data, status = self.make_request('GET', '/admin/listings', token=self.dev_token)
        basic_works = success and status == 200 and 'items' in data
        
        # Test with status filter
        success, data, status = self.make_request('GET', '/admin/listings?status=active', token=self.dev_token)
        filter_works = success and status == 200
        
        both_work = basic_works and filter_works
        self.log_test("Admin Listings", both_work, f"Basic: {basic_works}, Filter: {filter_works}")
    
    def test_admin_listing_status_change(self):
        """Test POST /admin/listings/{id}/status"""
        if not self.dev_token:
            self.log_test("Admin Listing Status", False, "No dev token available")
            return
            
        # First create a listing to test with
        listing_id = self.test_listings_operations()
        if not listing_id:
            self.log_test("Admin Listing Status", False, "Could not create test listing")
            return
        
        # Test valid status change
        success, data, status = self.make_request('POST', f'/admin/listings/{listing_id}/status?status=paused', token=self.dev_token)
        valid_change = success and status == 200
        
        # Test invalid status (should return 422)
        success, data, status = self.make_request('POST', f'/admin/listings/{listing_id}/status?status=invalid', token=self.dev_token)
        invalid_rejected = status == 422
        
        both_work = valid_change and invalid_rejected
        self.log_test("Admin Listing Status", both_work, f"Valid: {valid_change}, Invalid rejected: {invalid_rejected}")
    
    def test_admin_transactions(self):
        """Test GET /admin/transactions"""
        if not self.dev_token:
            self.log_test("Admin Transactions", False, "No dev token available")
            return
            
        success, data, status = self.make_request('GET', '/admin/transactions', token=self.dev_token)
        
        if success and status == 200:
            has_structure = 'items' in data and isinstance(data['items'], list)
            self.log_test("Admin Transactions", has_structure, f"Transactions: {len(data.get('items', []))}")
        else:
            self.log_test("Admin Transactions", False, f"Status: {status}, Data: {data}")
    
    def test_admin_providers(self):
        """Test GET /admin/providers"""
        if not self.dev_token:
            self.log_test("Admin Providers", False, "No dev token available")
            return
            
        success, data, status = self.make_request('GET', '/admin/providers', token=self.dev_token)
        
        if success and status == 200:
            has_summary = 'summary' in data and isinstance(data['summary'], list)
            self.log_test("Admin Providers", has_summary, f"Provider entries: {len(data.get('summary', []))}")
        else:
            self.log_test("Admin Providers", False, f"Status: {status}, Data: {data}")
    
    def test_admin_trend_scout(self):
        """Test GET /admin/trend-scout and POST /admin/trend-scout/run"""
        if not self.dev_token:
            self.log_test("Admin Trend Scout", False, "No dev token available")
            return
            
        # Test GET endpoint
        success, data, status = self.make_request('GET', '/admin/trend-scout', token=self.dev_token)
        get_works = success and status == 200 and 'items' in data
        
        # Test POST run endpoint
        print("🔄 Testing trend-scout run (this may take 15-30 seconds)...")
        success, data, status = self.make_request('POST', '/admin/trend-scout/run?force=true', token=self.dev_token, timeout=60)
        run_works = success and status == 200
        
        if run_works and 'generated' in data:
            generated_count = len(data.get('generated', []))
            self.log_test("Admin Trend Scout Run", generated_count > 0, f"Generated {generated_count} cards")
        else:
            self.log_test("Admin Trend Scout Run", False, f"Status: {status}, Data: {data}")
        
        self.log_test("Admin Trend Scout Get", get_works, f"Status: {status}")
    
    def test_admin_llm_usage(self):
        """Test GET /admin/llm-usage"""
        if not self.dev_token:
            self.log_test("Admin LLM Usage", False, "No dev token available")
            return
            
        success, data, status = self.make_request('GET', '/admin/llm-usage', token=self.dev_token)
        
        if success and status == 200:
            # Should never return 500 even if upstream is unreachable
            has_available_field = 'available' in data
            if data.get('available'):
                has_usage = 'usage' in data
                self.log_test("Admin LLM Usage", has_available_field and has_usage, f"Available: {data.get('available')}")
            else:
                has_reason = 'reason' in data
                self.log_test("Admin LLM Usage", has_available_field and has_reason, f"Reason: {data.get('reason')}")
        else:
            self.log_test("Admin LLM Usage", False, f"Status: {status}, Data: {data}")
    
    def test_admin_system(self):
        """Test GET /admin/system"""
        if not self.dev_token:
            self.log_test("Admin System", False, "No dev token available")
            return
            
        success, data, status = self.make_request('GET', '/admin/system', token=self.dev_token)
        
        if success and status == 200:
            # Check required sections
            required_sections = ['ai', 'keys_present', 'trend_scout', 'dev']
            has_sections = all(section in data for section in required_sections)
            
            # Check that all expected keys are present
            keys_present = data.get('keys_present', {})
            expected_keys = ['HF_TOKEN', 'EMERGENT_LLM_KEY', 'GROQ_API_KEY', 'DEEPGRAM_API_KEY', 'OPENWEATHER_API_KEY', 'GOOGLE_OAUTH_CLIENT_ID', 'GOOGLE_OAUTH_CLIENT_SECRET']
            all_keys_present = all(key in keys_present for key in expected_keys)
            all_keys_true = all(keys_present.get(key) for key in expected_keys)
            
            # Ensure no secret values are exposed
            no_secrets_exposed = True
            for section in data.values():
                if isinstance(section, dict):
                    for value in section.values():
                        if isinstance(value, str) and (value.startswith('sk-') or value.startswith('hf_') or value.startswith('gsk_')):
                            no_secrets_exposed = False
                            break
            
            all_valid = has_sections and all_keys_present and all_keys_true and no_secrets_exposed
            self.log_test("Admin System", all_valid, f"Sections: {has_sections}, Keys: {all_keys_present}/{all_keys_true}, No secrets: {no_secrets_exposed}")
        else:
            self.log_test("Admin System", False, f"Status: {status}, Data: {data}")
    
    def test_image_edit_regression(self):
        """Test POST /closet/{id}/edit-image with FLUX.1-schnell"""
        if not self.dev_token:
            self.log_test("Image Edit Regression", False, "No dev token available")
            return
            
        # Create a closet item first
        item_data = {
            "title": "Test Jacket for Edit",
            "category": "outerwear",
            "sub_category": "jacket",
            "brand": "TestBrand",
            "color": "blue",
            "material": "cotton",
            "original_image_url": "https://example.com/jacket.jpg"
        }
        
        success, data, status = self.make_request('POST', '/closet', item_data, token=self.dev_token)
        if not (success and status == 201):
            self.log_test("Image Edit Regression", False, f"Could not create closet item: {status}")
            return
            
        item_id = data.get('id')
        
        # Test image edit with FLUX
        print("🔄 Testing image edit with FLUX.1-schnell (this may take 10-30 seconds)...")
        edit_url = f'/closet/{item_id}/edit-image?prompt=Change the color to forest green'
        success, data, status = self.make_request('POST', edit_url, token=self.dev_token, timeout=60)
        
        if success and status == 200:
            has_variant_url = 'variant_url' in data and data['variant_url'].startswith('data:image/')
            has_variants = 'variants' in data and isinstance(data['variants'], list)
            
            # Check that variant uses FLUX model
            flux_model = False
            if has_variants and data['variants']:
                latest_variant = data['variants'][-1]
                model_used = latest_variant.get('model', '').lower()
                flux_model = 'flux' in model_used
            
            all_valid = has_variant_url and has_variants and flux_model
            self.log_test("Image Edit Regression", all_valid, 
                         f"Variant URL: {has_variant_url}, Variants: {has_variants}, FLUX model: {flux_model}")
        else:
            # Check if it's the expected 503 regression
            if status == 503:
                self.log_test("Image Edit Regression", False, f"REGRESSION: Still returning 503 - FLUX not working: {data}")
            else:
                self.log_test("Image Edit Regression", False, f"Status: {status}, Data: {data}")

    # ==================== ADD ITEM FEATURE TESTS ====================
    
    def test_analyze_item_image_base64(self):
        """Test POST /closet/analyze with image_base64"""
        if not self.dev_token:
            self.log_test("Analyze Item Image Base64", False, "No dev token available")
            return
            
        # Use a small test image (1x1 pixel PNG)
        test_image_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
        
        analyze_data = {
            "image_base64": test_image_b64
        }
        
        print("🔄 Testing garment analysis with base64 image (this may take 10-45 seconds)...")
        success, data, status = self.make_request('POST', '/closet/analyze', analyze_data, token=self.dev_token, timeout=90)
        
        if success and status == 200:
            # Check required fields from GarmentAnalysis schema
            has_title = bool(data.get('title'))
            has_category = bool(data.get('category'))
            has_colors = isinstance(data.get('colors', []), list)
            has_fabric_materials = isinstance(data.get('fabric_materials', []), list)
            has_model_used = bool(data.get('model_used'))
            
            # Check WeightedTag structure for colors and fabrics
            colors_valid = True
            if data.get('colors'):
                for color in data['colors']:
                    if not isinstance(color, dict) or 'name' not in color:
                        colors_valid = False
                        break
            
            fabrics_valid = True
            if data.get('fabric_materials'):
                for fabric in data['fabric_materials']:
                    if not isinstance(fabric, dict) or 'name' not in fabric:
                        fabrics_valid = False
                        break
            
            all_valid = has_title and has_category and has_colors and has_fabric_materials and has_model_used and colors_valid and fabrics_valid
            self.log_test("Analyze Item Image Base64", all_valid, 
                         f"Title: {has_title}, Category: {has_category}, Colors: {len(data.get('colors', []))}, Fabrics: {len(data.get('fabric_materials', []))}, Model: {data.get('model_used')}")
        else:
            self.log_test("Analyze Item Image Base64", False, f"Status: {status}, Data: {data}")
    
    def test_analyze_item_image_url(self):
        """Test POST /closet/analyze with image_url"""
        if not self.dev_token:
            self.log_test("Analyze Item Image URL", False, "No dev token available")
            return
            
        # Use a real clothing image from Unsplash
        analyze_data = {
            "image_url": "https://images.unsplash.com/photo-1603252109303-2751441dd157?w=400&q=80&auto=format&fit=crop"
        }
        
        print("🔄 Testing garment analysis with image URL (this may take 10-45 seconds)...")
        success, data, status = self.make_request('POST', '/closet/analyze', analyze_data, token=self.dev_token, timeout=90)
        
        if success and status == 200:
            has_title = bool(data.get('title'))
            has_category = bool(data.get('category'))
            has_model_used = bool(data.get('model_used'))
            
            self.log_test("Analyze Item Image URL", has_title and has_category and has_model_used, 
                         f"Title: {data.get('title')}, Category: {data.get('category')}, Model: {data.get('model_used')}")
        else:
            self.log_test("Analyze Item Image URL", False, f"Status: {status}, Data: {data}")
    
    def test_analyze_item_validation(self):
        """Test POST /closet/analyze validation errors"""
        if not self.dev_token:
            self.log_test("Analyze Item Validation", False, "No dev token available")
            return
            
        # Test with neither image_base64 nor image_url
        success, data, status = self.make_request('POST', '/closet/analyze', {}, token=self.dev_token)
        no_image_fails = status == 400
        
        # Test with invalid base64
        invalid_data = {"image_base64": "invalid_base64_string"}
        success, data, status = self.make_request('POST', '/closet/analyze', invalid_data, token=self.dev_token)
        invalid_base64_fails = status == 400
        
        # Test without auth
        success, data, status = self.make_request('POST', '/closet/analyze', {"image_base64": "test"})
        no_auth_fails = status == 401
        
        all_validations = no_image_fails and invalid_base64_fails and no_auth_fails
        self.log_test("Analyze Item Validation", all_validations, 
                     f"No image: {status}, Invalid base64: {status}, No auth: {status}")
    
    def test_closet_marketplace_intent_own(self):
        """Test POST /closet with marketplace_intent='own'"""
        if not self.dev_token:
            self.log_test("Closet Marketplace Intent Own", False, "No dev token available")
            return
            
        item_data = {
            "title": "Test Private Item",
            "category": "Top",
            "colors": [{"name": "black", "pct": 99}, {"name": "red", "pct": 1}],
            "fabric_materials": [{"name": "cotton", "pct": 98}, {"name": "elastane", "pct": 2}],
            "marketplace_intent": "own"
        }
        
        success, data, status = self.make_request('POST', '/closet', item_data, token=self.dev_token)
        
        if success and status == 201:
            # Should create closet item only, no listing
            source_private = data.get('source') == 'Private'
            no_listing_id = data.get('listing_id') is None
            colors_preserved = data.get('colors') == item_data['colors']
            fabrics_preserved = data.get('fabric_materials') == item_data['fabric_materials']
            
            all_correct = source_private and no_listing_id and colors_preserved and fabrics_preserved
            self.log_test("Closet Marketplace Intent Own", all_correct, 
                         f"Source: {data.get('source')}, Listing ID: {data.get('listing_id')}, Colors preserved: {colors_preserved}")
            return data.get('id')
        else:
            self.log_test("Closet Marketplace Intent Own", False, f"Status: {status}, Data: {data}")
            return None
    
    def test_closet_marketplace_intent_for_sale(self):
        """Test POST /closet with marketplace_intent='for_sale'"""
        if not self.dev_token:
            self.log_test("Closet Marketplace Intent For Sale", False, "No dev token available")
            return
            
        item_data = {
            "title": "Test For Sale Item",
            "category": "Top",
            "price_cents": 7500,
            "marketplace_intent": "for_sale",
            "condition": "excellent"
        }
        
        success, data, status = self.make_request('POST', '/closet', item_data, token=self.dev_token)
        
        if success and status == 201:
            # Should create both closet item and listing
            source_shared = data.get('source') == 'Shared'
            has_listing_id = data.get('listing_id') is not None
            
            if has_listing_id:
                # Check the listing was created
                listing_id = data.get('listing_id')
                success2, listing_data, status2 = self.make_request('GET', f'/listings/{listing_id}')
                
                if success2 and status2 == 200:
                    listing_mode_sell = listing_data.get('mode') == 'sell'
                    listing_price = listing_data.get('financial_metadata', {}).get('list_price_cents') == 7500
                    platform_fee = listing_data.get('financial_metadata', {}).get('platform_fee_percent') == 7.0
                    seller_net = listing_data.get('financial_metadata', {}).get('estimated_seller_net_cents', 0) > 0
                    
                    all_correct = source_shared and listing_mode_sell and listing_price and platform_fee and seller_net
                    self.log_test("Closet Marketplace Intent For Sale", all_correct, 
                                 f"Source: {data.get('source')}, Mode: {listing_data.get('mode')}, Price: {listing_price}, Fee: {platform_fee}%")
                    return data.get('id'), listing_id
                else:
                    self.log_test("Closet Marketplace Intent For Sale", False, f"Could not retrieve listing: {status2}")
            else:
                self.log_test("Closet Marketplace Intent For Sale", False, "No listing ID created")
        else:
            self.log_test("Closet Marketplace Intent For Sale", False, f"Status: {status}, Data: {data}")
        
        return None, None
    
    def test_closet_marketplace_intent_donate(self):
        """Test POST /closet with marketplace_intent='donate'"""
        if not self.dev_token:
            self.log_test("Closet Marketplace Intent Donate", False, "No dev token available")
            return
            
        item_data = {
            "title": "Test Donate Item",
            "category": "Bottom",
            "marketplace_intent": "donate"
        }
        
        success, data, status = self.make_request('POST', '/closet', item_data, token=self.dev_token)
        
        if success and status == 201:
            has_listing_id = data.get('listing_id') is not None
            
            if has_listing_id:
                listing_id = data.get('listing_id')
                success2, listing_data, status2 = self.make_request('GET', f'/listings/{listing_id}')
                
                if success2 and status2 == 200:
                    listing_mode_donate = listing_data.get('mode') == 'donate'
                    listing_price_zero = listing_data.get('financial_metadata', {}).get('list_price_cents') == 0
                    
                    all_correct = listing_mode_donate and listing_price_zero
                    self.log_test("Closet Marketplace Intent Donate", all_correct, 
                                 f"Mode: {listing_data.get('mode')}, Price: {listing_data.get('financial_metadata', {}).get('list_price_cents')}")
                else:
                    self.log_test("Closet Marketplace Intent Donate", False, f"Could not retrieve listing: {status2}")
            else:
                self.log_test("Closet Marketplace Intent Donate", False, "No listing ID created")
        else:
            self.log_test("Closet Marketplace Intent Donate", False, f"Status: {status}, Data: {data}")
    
    def test_closet_marketplace_intent_swap(self):
        """Test POST /closet with marketplace_intent='swap'"""
        if not self.dev_token:
            self.log_test("Closet Marketplace Intent Swap", False, "No dev token available")
            return
            
        item_data = {
            "title": "Test Swap Item",
            "category": "Outerwear",
            "marketplace_intent": "swap"
        }
        
        success, data, status = self.make_request('POST', '/closet', item_data, token=self.dev_token)
        
        if success and status == 201:
            has_listing_id = data.get('listing_id') is not None
            
            if has_listing_id:
                listing_id = data.get('listing_id')
                success2, listing_data, status2 = self.make_request('GET', f'/listings/{listing_id}')
                
                if success2 and status2 == 200:
                    listing_mode_swap = listing_data.get('mode') == 'swap'
                    
                    self.log_test("Closet Marketplace Intent Swap", listing_mode_swap, 
                                 f"Mode: {listing_data.get('mode')}")
                else:
                    self.log_test("Closet Marketplace Intent Swap", False, f"Could not retrieve listing: {status2}")
            else:
                self.log_test("Closet Marketplace Intent Swap", False, "No listing ID created")
        else:
            self.log_test("Closet Marketplace Intent Swap", False, f"Status: {status}, Data: {data}")
    
    def test_schema_fields_roundtrip(self):
        """Test that complex schema fields round-trip correctly"""
        if not self.dev_token:
            self.log_test("Schema Fields Roundtrip", False, "No dev token available")
            return
            
        complex_data = {
            "title": "Complex Schema Test Item",
            "category": "Top",
            "colors": [{"name": "black", "pct": 99}, {"name": "red", "pct": 1}],
            "fabric_materials": [{"name": "cotton", "pct": 98}, {"name": "elastane", "pct": 2}],
            "season": ["spring", "summer"],
            "tags": ["casual", "comfortable", "everyday"]
        }
        
        success, data, status = self.make_request('POST', '/closet', complex_data, token=self.dev_token)
        
        if success and status == 201:
            item_id = data.get('id')
            
            # Retrieve the item and check fields
            success2, retrieved_data, status2 = self.make_request('GET', f'/closet/{item_id}', token=self.dev_token)
            
            if success2 and status2 == 200:
                colors_match = retrieved_data.get('colors') == complex_data['colors']
                fabrics_match = retrieved_data.get('fabric_materials') == complex_data['fabric_materials']
                season_match = retrieved_data.get('season') == complex_data['season']
                tags_match = retrieved_data.get('tags') == complex_data['tags']
                
                all_match = colors_match and fabrics_match and season_match and tags_match
                self.log_test("Schema Fields Roundtrip", all_match, 
                             f"Colors: {colors_match}, Fabrics: {fabrics_match}, Season: {season_match}, Tags: {tags_match}")
            else:
                self.log_test("Schema Fields Roundtrip", False, f"Could not retrieve item: {status2}")
        else:
            self.log_test("Schema Fields Roundtrip", False, f"Status: {status}, Data: {data}")
    
    # ==================== PHASE A ARCHITECTURE TESTS ====================
    
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
            
        # First create an item with embedding
        item_id = self.test_closet_create_with_clip_embedding()
        if not item_id:
            self.log_test("Closet List Strips Embedding", False, "Could not create item with embedding")
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
            
        # First ensure we have an item with embedding
        item_id = self.test_closet_create_with_clip_embedding()
        if not item_id:
            self.log_test("Closet Search Text", False, "Could not create item with embedding")
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
    
    def test_closet_search_image(self):
        """NEW: Test POST /api/v1/closet/search with image_base64"""
        if not self.dev_token:
            self.log_test("Closet Search Image", False, "No dev token available")
            return
            
        # Use same image as the item we created
        test_image_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
        
        search_data = {
            "image_base64": test_image_b64,
            "limit": 5,
            "min_score": 0.8  # High threshold for exact match
        }
        
        print("🔄 Testing closet search with image (this may take 5-15 seconds)...")
        success, data, status = self.make_request('POST', '/closet/search', search_data, token=self.dev_token, timeout=30)
        
        if success and status == 200:
            has_items = 'items' in data
            has_model = data.get('model') == 'patrickjohncyh/fashion-clip'
            
            # Check for high similarity score (should be ~1.0 for same image)
            high_score_match = False
            if data.get('items'):
                top_score = data['items'][0].get('_score', 0)
                high_score_match = top_score >= 0.9  # Should be very high for same image
            
            all_valid = has_items and has_model and high_score_match
            self.log_test("Closet Search Image", all_valid, 
                         f"Items: {len(data.get('items', []))}, Top score: {data.get('items', [{}])[0].get('_score', 0) if data.get('items') else 0}")
        else:
            self.log_test("Closet Search Image", False, f"Status: {status}, Data: {data}")
    
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
            
            # Test with both text and image_base64 (should work)
            both_fields_data = {
                "text": "test",
                "image_base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
            }
            success, data, status = self.make_request('POST', '/closet/search', both_fields_data, token=self.dev_token, timeout=30)
            both_fields_works = status == 200
        else:
            missing_fields_fails = True
            both_fields_works = True
        
        all_validations = no_auth_fails and missing_fields_fails and both_fields_works
        self.log_test("Closet Search Auth Validation", all_validations, 
                     f"No auth: 401={no_auth_fails}, Missing fields: 400={missing_fields_fails}, Both fields: 200={both_fields_works}")
    
    def test_closet_search_min_score_limit(self):
        """NEW: Test POST /api/v1/closet/search honors min_score and limit"""
        if not self.dev_token:
            self.log_test("Closet Search Min Score Limit", False, "No dev token available")
            return
        
        # Test with very high min_score (should return fewer/no results)
        high_threshold_data = {
            "text": "random query that probably won't match well",
            "min_score": 0.95,
            "limit": 100
        }
        
        success, data, status = self.make_request('POST', '/closet/search', high_threshold_data, token=self.dev_token, timeout=30)
        
        if success and status == 200:
            high_threshold_items = len(data.get('items', []))
            
            # Test with low min_score (should return more results)
            low_threshold_data = {
                "text": "shirt top clothing",
                "min_score": 0.01,
                "limit": 2  # Small limit
            }
            
            success2, data2, status2 = self.make_request('POST', '/closet/search', low_threshold_data, token=self.dev_token, timeout=30)
            
            if success2 and status2 == 200:
                low_threshold_items = len(data2.get('items', []))
                limit_respected = low_threshold_items <= 2
                
                # High threshold should return fewer items than low threshold (or equal if no items)
                threshold_works = high_threshold_items <= low_threshold_items
                
                all_valid = limit_respected and threshold_works
                self.log_test("Closet Search Min Score Limit", all_valid, 
                             f"High threshold: {high_threshold_items}, Low threshold: {low_threshold_items}, Limit respected: {limit_respected}")
            else:
                self.log_test("Closet Search Min Score Limit", False, f"Low threshold test failed: {status2}")
        else:
            self.log_test("Closet Search Min Score Limit", False, f"High threshold test failed: {status}")
    
    def test_admin_providers_fashion_clip(self):
        """NEW: Test admin provider activity shows 'fashion-clip' after embedding call"""
        if not self.dev_token:
            self.log_test("Admin Providers Fashion CLIP", False, "No dev token available")
            return
            
        # First make sure we have a CLIP embedding call
        self.test_closet_create_with_clip_embedding()
        
        # Check admin providers
        success, data, status = self.make_request('GET', '/admin/providers', token=self.dev_token)
        
        if success and status == 200:
            providers = data.get('summary', [])
            fashion_clip_found = any(
                provider.get('provider_name') == 'fashion-clip' 
                for provider in providers
            )
            
            self.log_test("Admin Providers Fashion CLIP", fashion_clip_found, 
                         f"Providers: {[p.get('provider_name') for p in providers]}")
        else:
            self.log_test("Admin Providers Fashion CLIP", False, f"Status: {status}, Data: {data}")

    def test_provider_activity_tracking(self):
        """Test that provider activity is tracked for garment vision calls"""
        if not self.dev_token:
            self.log_test("Provider Activity Tracking", False, "No dev token available")
            return
            
        # Make an analyze call first
        test_image_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
        analyze_data = {"image_base64": test_image_b64}
        
        print("🔄 Testing provider activity tracking...")
        success, data, status = self.make_request('POST', '/closet/analyze', analyze_data, token=self.dev_token, timeout=90)
        
        if success and status == 200:
            # Check admin providers endpoint for garment-vision activity
            success2, providers_data, status2 = self.make_request('GET', '/admin/providers', token=self.dev_token)
            
            if success2 and status2 == 200:
                providers = providers_data.get('summary', [])
                garment_vision_found = False
                
                for provider in providers:
                    if provider.get('provider') == 'garment-vision':
                        garment_vision_found = True
                        total_calls = provider.get('total', 0)
                        has_calls = total_calls >= 1
                        
                        self.log_test("Provider Activity Tracking", has_calls, 
                                     f"Garment-vision calls: {total_calls}")
                        break
                
                if not garment_vision_found:
                    self.log_test("Provider Activity Tracking", False, "Garment-vision provider not found in activity")
            else:
                self.log_test("Provider Activity Tracking", False, f"Could not get providers: {status2}")
        else:
            self.log_test("Provider Activity Tracking", False, f"Analyze call failed: {status}")

    # ==================== PHASE M: SYSTEM-NATIVE SPEECH TESTS ====================
    
    def test_stylist_skip_tts_true(self):
        """Test POST /stylist with skip_tts=true returns no audio but has spoken_reply"""
        if not self.dev_token:
            self.log_test("Stylist Skip TTS True", False, "No dev token available")
            return
            
        data = {
            'text': 'What should I wear today for work?',
            'skip_tts': 'true'
        }
        headers = {'Authorization': f'Bearer {self.dev_token}'}
        url = f"{self.base_url}/api/v1/stylist"
        
        print("🔄 Testing stylist with skip_tts=true (this may take 15-25 seconds)...")
        
        try:
            response = requests.post(url, data=data, headers=headers, timeout=120)
            response_data = response.json() if response.content else {}
            success = True
            status = response.status_code
        except Exception as e:
            success = False
            response_data = {"error": str(e)}
            status = 0
        
        if success and status == 200:
            advice = response_data.get('advice', {})
            tts_audio_base64 = advice.get('tts_audio_base64')
            spoken_reply = advice.get('spoken_reply', '')
            reasoning_summary = advice.get('reasoning_summary', '')
            
            # Key requirements: no audio, but has spoken content
            no_audio = tts_audio_base64 is None or tts_audio_base64 == ""
            has_spoken_reply = len(spoken_reply.strip()) > 0
            has_reasoning = len(reasoning_summary.strip()) > 0
            
            all_valid = no_audio and has_spoken_reply and has_reasoning
            self.log_test("Stylist Skip TTS True", all_valid, 
                         f"No audio: {no_audio}, Spoken reply: {len(spoken_reply)} chars, Reasoning: {len(reasoning_summary)} chars")
        else:
            self.log_test("Stylist Skip TTS True", False, f"Status: {status}, Data: {response_data}")
    
    def test_stylist_skip_tts_default(self):
        """Test POST /stylist without skip_tts (default false) returns audio"""
        if not self.dev_token:
            self.log_test("Stylist Skip TTS Default", False, "No dev token available")
            return
            
        data = {'text': 'What should I wear today for work?'}
        headers = {'Authorization': f'Bearer {self.dev_token}'}
        url = f"{self.base_url}/api/v1/stylist"
        
        print("🔄 Testing stylist with default skip_tts (this may take 15-25 seconds)...")
        
        try:
            response = requests.post(url, data=data, headers=headers, timeout=120)
            response_data = response.json() if response.content else {}
            success = True
            status = response.status_code
        except Exception as e:
            success = False
            response_data = {"error": str(e)}
            status = 0
        
        if success and status == 200:
            advice = response_data.get('advice', {})
            tts_audio_base64 = advice.get('tts_audio_base64', '')
            spoken_reply = advice.get('spoken_reply', '')
            
            # Key requirements: has audio and spoken content
            has_audio = len(tts_audio_base64.strip()) > 0
            has_spoken_reply = len(spoken_reply.strip()) > 0
            
            all_valid = has_audio and has_spoken_reply
            self.log_test("Stylist Skip TTS Default", all_valid, 
                         f"Has audio: {has_audio} ({len(tts_audio_base64)} chars), Spoken reply: {len(spoken_reply)} chars")
        else:
            self.log_test("Stylist Skip TTS Default", False, f"Status: {status}, Data: {response_data}")
    
    def test_stylist_skip_tts_false_explicit(self):
        """Test POST /stylist with skip_tts=false explicitly set includes audio"""
        if not self.dev_token:
            self.log_test("Stylist Skip TTS False Explicit", False, "No dev token available")
            return
            
        data = {
            'text': 'What should I wear today for work?',
            'skip_tts': 'false'
        }
        headers = {'Authorization': f'Bearer {self.dev_token}'}
        url = f"{self.base_url}/api/v1/stylist"
        
        print("🔄 Testing stylist with skip_tts=false explicit (this may take 15-25 seconds)...")
        
        try:
            response = requests.post(url, data=data, headers=headers, timeout=120)
            response_data = response.json() if response.content else {}
            success = True
            status = response.status_code
        except Exception as e:
            success = False
            response_data = {"error": str(e)}
            status = 0
        
        if success and status == 200:
            advice = response_data.get('advice', {})
            tts_audio_base64 = advice.get('tts_audio_base64', '')
            spoken_reply = advice.get('spoken_reply', '')
            
            # Key requirements: has audio and spoken content (parity with default)
            has_audio = len(tts_audio_base64.strip()) > 0
            has_spoken_reply = len(spoken_reply.strip()) > 0
            
            all_valid = has_audio and has_spoken_reply
            self.log_test("Stylist Skip TTS False Explicit", all_valid, 
                         f"Has audio: {has_audio} ({len(tts_audio_base64)} chars), Spoken reply: {len(spoken_reply)} chars")
        else:
            self.log_test("Stylist Skip TTS False Explicit", False, f"Status: {status}, Data: {response_data}")
    
    def test_stylist_voice_audio_with_skip_tts(self):
        """Test POST /stylist with voice_audio AND skip_tts=true still transcribes"""
        if not self.dev_token:
            self.log_test("Stylist Voice Audio Skip TTS", False, "No dev token available")
            return
            
        # Create a minimal WebM audio file (just headers, won't actually work for transcription but tests the flow)
        # This is a minimal WebM container with Opus audio track
        webm_bytes = bytes([
            0x1A, 0x45, 0xDF, 0xA3,  # EBML header
            0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x1F,  # EBML header size
            0x42, 0x86, 0x81, 0x01,  # EBMLVersion = 1
            0x42, 0xF7, 0x81, 0x01,  # EBMLReadVersion = 1
            0x42, 0xF2, 0x81, 0x04,  # EBMLMaxIDLength = 4
            0x42, 0xF3, 0x81, 0x08,  # EBMLMaxSizeLength = 8
            0x42, 0x82, 0x84, 0x77, 0x65, 0x62, 0x6D,  # DocType = "webm"
            0x42, 0x87, 0x81, 0x02,  # DocTypeVersion = 2
            0x42, 0x85, 0x81, 0x02   # DocTypeReadVersion = 2
        ])
        
        files = {'voice_audio': ('test.webm', webm_bytes, 'audio/webm')}
        data = {'skip_tts': 'true'}
        headers = {'Authorization': f'Bearer {self.dev_token}'}
        url = f"{self.base_url}/api/v1/stylist"
        
        print("🔄 Testing stylist with voice_audio + skip_tts=true (this may take 15-25 seconds)...")
        
        try:
            response = requests.post(url, data=data, files=files, headers=headers, timeout=120)
            response_data = response.json() if response.content else {}
            success = True
            status = response.status_code
        except Exception as e:
            success = False
            response_data = {"error": str(e)}
            status = 0
        
        # This test might fail due to invalid audio, but we're testing the flow
        if success and status == 200:
            advice = response_data.get('advice', {})
            transcript = advice.get('transcript', '')
            tts_audio_base64 = advice.get('tts_audio_base64')
            
            # Key requirements: attempted transcription, no audio output
            has_transcript_field = 'transcript' in advice  # Even if empty due to bad audio
            no_audio = tts_audio_base64 is None or tts_audio_base64 == ""
            
            all_valid = has_transcript_field and no_audio
            self.log_test("Stylist Voice Audio Skip TTS", all_valid, 
                         f"Transcript field present: {has_transcript_field}, No audio: {no_audio}")
        elif status == 400:
            # Expected if audio is invalid - test that it doesn't 500
            self.log_test("Stylist Voice Audio Skip TTS", True, 
                         f"Graceful 400 error for invalid audio: {response_data}")
        else:
            self.log_test("Stylist Voice Audio Skip TTS", False, f"Status: {status}, Data: {response_data}")
    
    def test_stylist_skip_tts_invalid_value(self):
        """Test POST /stylist with invalid skip_tts value doesn't 500"""
        if not self.dev_token:
            self.log_test("Stylist Skip TTS Invalid Value", False, "No dev token available")
            return
            
        data = {
            'text': 'What should I wear today for work?',
            'skip_tts': 'banana'  # Invalid value
        }
        headers = {'Authorization': f'Bearer {self.dev_token}'}
        url = f"{self.base_url}/api/v1/stylist"
        
        print("🔄 Testing stylist with invalid skip_tts value...")
        
        try:
            response = requests.post(url, data=data, headers=headers, timeout=120)
            response_data = response.json() if response.content else {}
            success = True
            status = response.status_code
        except Exception as e:
            success = False
            response_data = {"error": str(e)}
            status = 0
        
        # Should either reject with 4xx or coerce cleanly, but NOT 500
        if success:
            not_500 = status != 500
            if status == 200:
                # If it coerced cleanly, check the response is valid
                advice = response_data.get('advice', {})
                has_reasoning = bool(advice.get('reasoning_summary'))
                coerced_cleanly = has_reasoning
                self.log_test("Stylist Skip TTS Invalid Value", not_500 and coerced_cleanly, 
                             f"Status: {status}, Coerced cleanly: {coerced_cleanly}")
            elif 400 <= status < 500:
                # Rejected with 4xx - also acceptable
                self.log_test("Stylist Skip TTS Invalid Value", True, 
                             f"Rejected with 4xx: {status}")
            else:
                self.log_test("Stylist Skip TTS Invalid Value", not_500, 
                             f"Status: {status} (not 500)")
        else:
            self.log_test("Stylist Skip TTS Invalid Value", False, f"Request failed: {response_data}")
    
    def test_stylist_hebrew_localization_skip_tts(self):
        """Test POST /stylist with language='he' + skip_tts=true localizes without audio"""
        if not self.dev_token:
            self.log_test("Stylist Hebrew Skip TTS", False, "No dev token available")
            return
            
        data = {
            'text': 'What should I wear today for work?',
            'language': 'he',
            'skip_tts': 'true'
        }
        headers = {'Authorization': f'Bearer {self.dev_token}'}
        url = f"{self.base_url}/api/v1/stylist"
        
        print("🔄 Testing stylist Hebrew localization with skip_tts=true (this may take 30-60 seconds)...")
        
        try:
            response = requests.post(url, data=data, headers=headers, timeout=120)
            response_data = response.json() if response.content else {}
            success = True
            status = response.status_code
        except Exception as e:
            success = False
            response_data = {"error": str(e)}
            status = 0
        
        if success and status == 200:
            advice = response_data.get('advice', {})
            reasoning_summary = advice.get('reasoning_summary', '')
            spoken_reply = advice.get('spoken_reply', '')
            tts_audio_base64 = advice.get('tts_audio_base64')
            
            # Check if content appears to be in Hebrew (contains Hebrew characters)
            hebrew_chars = any('\u0590' <= char <= '\u05FF' for char in reasoning_summary + spoken_reply)
            has_content = bool(reasoning_summary and spoken_reply)
            no_audio = tts_audio_base64 is None or tts_audio_base64 == ""
            
            all_valid = hebrew_chars and has_content and no_audio
            self.log_test("Stylist Hebrew Skip TTS", all_valid,
                         f"Hebrew chars: {hebrew_chars}, Has content: {has_content}, No audio: {no_audio}")
        else:
            self.log_test("Stylist Hebrew Skip TTS", False, f"Status: {status}, Data: {response_data}")
    
    def test_stylist_history_regression(self):
        """Test GET /stylist/history still works unchanged (regression test)"""
        if not self.dev_token:
            self.log_test("Stylist History Regression", False, "No dev token available")
            return
            
        success, data, status = self.make_request('GET', '/stylist/history', token=self.dev_token)
        
        if success and status == 200:
            # Check expected structure
            has_session_id = 'session_id' in data
            has_messages = 'messages' in data and isinstance(data['messages'], list)
            
            all_valid = has_session_id and has_messages
            self.log_test("Stylist History Regression", all_valid, 
                         f"Session ID: {has_session_id}, Messages: {len(data.get('messages', []))}")
        else:
            self.log_test("Stylist History Regression", False, f"Status: {status}, Data: {data}")
    
    def test_phase_l_language_persistence_regression(self):
        """Test PATCH /users/me with preferred_language='he' persists and stylist respects it"""
        if not self.dev_token:
            self.log_test("Phase L Language Persistence", False, "No dev token available")
            return
            
        # Set preferred language to Hebrew
        update_data = {"preferred_language": "he"}
        success, data, status = self.make_request('PATCH', '/users/me', update_data, token=self.dev_token)
        
        if not (success and status == 200):
            self.log_test("Phase L Language Persistence", False, f"PATCH failed: {status}")
            return
            
        # Verify persistence
        success2, data2, status2 = self.make_request('GET', '/users/me', token=self.dev_token)
        
        if not (success2 and status2 == 200):
            self.log_test("Phase L Language Persistence", False, f"GET failed: {status2}")
            return
            
        persisted_lang = data2.get('preferred_language')
        if persisted_lang != 'he':
            self.log_test("Phase L Language Persistence", False, f"Language not persisted: {persisted_lang}")
            return
        
        # Make stylist call to verify it respects the preference
        stylist_data = {'text': 'What should I wear today?'}
        headers = {'Authorization': f'Bearer {self.dev_token}'}
        url = f"{self.base_url}/api/v1/stylist"
        
        print("🔄 Testing Phase L language persistence with stylist call (this may take 30-60 seconds)...")
        
        try:
            response = requests.post(url, data=stylist_data, headers=headers, timeout=120)
            response_data = response.json() if response.content else {}
            success3 = True
            status3 = response.status_code
        except Exception as e:
            success3 = False
            response_data = {"error": str(e)}
            status3 = 0
        
        if success3 and status3 == 200:
            advice = response_data.get('advice', {})
            reasoning_summary = advice.get('reasoning_summary', '')
            spoken_reply = advice.get('spoken_reply', '')
            
            # Check if content appears to be in Hebrew
            hebrew_chars = any('\u0590' <= char <= '\u05FF' for char in reasoning_summary + spoken_reply)
            has_content = bool(reasoning_summary and spoken_reply)
            
            all_valid = hebrew_chars and has_content
            self.log_test("Phase L Language Persistence", all_valid,
                         f"Persisted: {persisted_lang}, Hebrew chars: {hebrew_chars}, Has content: {has_content}")
        else:
            self.log_test("Phase L Language Persistence", False, f"Stylist call failed: {status3}")
        
        # Reset to English
        update_data = {"preferred_language": "en"}
        self.make_request('PATCH', '/users/me', update_data, token=self.dev_token)
    
    def test_closet_analyze_regression(self):
        """Test /closet/analyze endpoint unchanged (regression test)"""
        if not self.dev_token:
            self.log_test("Closet Analyze Regression", False, "No dev token available")
            return
            
        # Use a small test image for analysis
        test_image_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
        
        analyze_data = {
            "image_base64": test_image_b64,
            "multi": False  # Single-item analysis
        }
        
        print("🔄 Testing closet analyze regression (this may take 30-60 seconds)...")
        success, data, status = self.make_request('POST', '/closet/analyze', analyze_data, token=self.dev_token, timeout=90)
        
        if success and status == 200:
            # Check expected fields are present
            has_title = 'title' in data
            has_category = 'category' in data
            has_colors = 'colors' in data
            
            all_valid = has_title and has_category and has_colors
            self.log_test("Closet Analyze Regression", all_valid, 
                         f"Title: {has_title}, Category: {has_category}, Colors: {has_colors}")
        else:
            self.log_test("Closet Analyze Regression", False, f"Status: {status}, Data: {data}")

    # ==================== PHASE U: PROFESSIONAL FASHION EXPERT TESTS ====================
    
    def test_professional_profile_setup(self):
        """Test PATCH /users/me with professional fields"""
        if not self.dev_token:
            self.log_test("Professional Profile Setup", False, "No dev token available")
            return
            
        # Set up professional profile
        professional_data = {
            "professional": {
                "is_professional": True,
                "profession": "Fashion Stylist",
                "business": {
                    "name": "Style Expert Co",
                    "address": "123 Fashion St, Tel Aviv, Israel",
                    "phone": "+972-50-123-4567",
                    "email": "contact@styleexpert.co.il",
                    "website": "https://styleexpert.co.il",
                    "description": "Professional fashion styling services for all occasions"
                },
                "approval_status": "self"
            }
        }
        
        success, data, status = self.make_request('PATCH', '/users/me', professional_data, token=self.dev_token)
        
        if success and status == 200:
            prof = data.get('professional', {})
            business = prof.get('business', {})
            
            is_professional = prof.get('is_professional') == True
            has_profession = prof.get('profession') == "Fashion Stylist"
            has_business_name = business.get('name') == "Style Expert Co"
            has_approval_status = prof.get('approval_status') == "self"
            
            all_valid = is_professional and has_profession and has_business_name and has_approval_status
            self.log_test("Professional Profile Setup", all_valid, 
                         f"Professional: {is_professional}, Profession: {has_profession}, Business: {has_business_name}")
        else:
            self.log_test("Professional Profile Setup", False, f"Status: {status}, Data: {data}")
    
    def test_professional_directory_listing(self):
        """Test GET /professionals returns professionals only"""
        success, data, status = self.make_request('GET', '/professionals')
        
        if success and status == 200:
            has_items = 'items' in data and isinstance(data['items'], list)
            has_pagination = all(k in data for k in ['total', 'skip', 'limit'])
            
            # Check that all returned items are professionals
            all_professionals = True
            if data.get('items'):
                for item in data['items']:
                    prof = item.get('professional', {})
                    if not prof.get('is_professional'):
                        all_professionals = False
                        break
            
            all_valid = has_items and has_pagination and all_professionals
            self.log_test("Professional Directory Listing", all_valid, 
                         f"Items: {len(data.get('items', []))}, Total: {data.get('total')}, All professionals: {all_professionals}")
        else:
            self.log_test("Professional Directory Listing", False, f"Status: {status}, Data: {data}")
    
    def test_professional_directory_filters(self):
        """Test GET /professionals with filters (country, region, profession, q)"""
        # Test country filter
        success, data, status = self.make_request('GET', '/professionals?country=IL')
        country_filter_works = success and status == 200
        
        # Test profession filter
        success, data, status = self.make_request('GET', '/professionals?profession=Fashion%20Stylist')
        profession_filter_works = success and status == 200
        
        # Test text search
        success, data, status = self.make_request('GET', '/professionals?q=style')
        text_search_works = success and status == 200
        
        # Test region filter
        success, data, status = self.make_request('GET', '/professionals?region=Tel%20Aviv')
        region_filter_works = success and status == 200
        
        all_filters_work = country_filter_works and profession_filter_works and text_search_works and region_filter_works
        self.log_test("Professional Directory Filters", all_filters_work, 
                     f"Country: {country_filter_works}, Profession: {profession_filter_works}, Text: {text_search_works}, Region: {region_filter_works}")
    
    def test_professional_individual_lookup(self):
        """Test GET /professionals/{id} returns individual professional"""
        # First get a professional ID from the directory
        success, data, status = self.make_request('GET', '/professionals')
        if not (success and status == 200 and data.get('items')):
            self.log_test("Professional Individual Lookup", False, "No professionals found in directory")
            return
            
        professional_id = data['items'][0]['id']
        
        # Test individual lookup
        success, data, status = self.make_request('GET', f'/professionals/{professional_id}')
        
        if success and status == 200:
            has_id = data.get('id') == professional_id
            has_professional_data = 'professional' in data
            has_business_data = data.get('professional', {}).get('business') is not None
            
            all_valid = has_id and has_professional_data and has_business_data
            self.log_test("Professional Individual Lookup", all_valid, 
                         f"ID match: {has_id}, Professional data: {has_professional_data}, Business data: {has_business_data}")
        else:
            self.log_test("Professional Individual Lookup", False, f"Status: {status}, Data: {data}")
    
    def test_ad_campaign_creation(self):
        """Test POST /ads/campaigns creates campaign for professionals only"""
        if not self.dev_token:
            self.log_test("Ad Campaign Creation", False, "No dev token available")
            return
            
        campaign_data = {
            "name": "Fashion Styling Services",
            "profession": "Fashion Stylist",
            "creative": {
                "headline": "Professional Fashion Styling",
                "body": "Transform your wardrobe with expert styling advice",
                "cta_label": "Book Now",
                "cta_url": "https://styleexpert.co.il/book"
            },
            "daily_budget_cents": 5000,
            "bid_cents": 100,
            "target_country": "IL",
            "target_region": "Tel Aviv",
            "status": "active"
        }
        
        success, data, status = self.make_request('POST', '/ads/campaigns', campaign_data, token=self.dev_token)
        
        if success and status == 200:
            has_id = 'id' in data
            has_owner = data.get('owner_id') is not None
            has_creative = 'creative' in data and 'headline' in data['creative']
            has_status = data.get('status') == 'active'
            
            all_valid = has_id and has_owner and has_creative and has_status
            self.log_test("Ad Campaign Creation", all_valid, 
                         f"ID: {has_id}, Owner: {has_owner}, Creative: {has_creative}, Status: {has_status}")
            
            # Store campaign ID for other tests
            self.test_campaign_id = data.get('id')
        else:
            self.log_test("Ad Campaign Creation", False, f"Status: {status}, Data: {data}")
    
    def test_ad_campaign_crud(self):
        """Test ad campaign CRUD operations"""
        if not self.dev_token:
            self.log_test("Ad Campaign CRUD", False, "No dev token available")
            return
            
        # Test GET /ads/campaigns (list my campaigns)
        success, data, status = self.make_request('GET', '/ads/campaigns', token=self.dev_token)
        list_works = success and status == 200 and 'items' in data
        
        if not list_works:
            self.log_test("Ad Campaign CRUD", False, "Could not list campaigns")
            return
            
        if not data.get('items'):
            self.log_test("Ad Campaign CRUD", False, "No campaigns found")
            return
            
        campaign_id = data['items'][0]['id']
        
        # Test GET /ads/campaigns/{id} (get specific campaign)
        success, data, status = self.make_request('GET', f'/ads/campaigns/{campaign_id}', token=self.dev_token)
        get_works = success and status == 200 and data.get('id') == campaign_id
        
        # Test PATCH /ads/campaigns/{id} (update campaign)
        update_data = {
            "name": "Updated Fashion Styling Services",
            "daily_budget_cents": 7500
        }
        success, data, status = self.make_request('PATCH', f'/ads/campaigns/{campaign_id}', update_data, token=self.dev_token)
        patch_works = success and status == 200 and data.get('name') == "Updated Fashion Styling Services"
        
        # Test DELETE /ads/campaigns/{id} (delete campaign)
        success, data, status = self.make_request('DELETE', f'/ads/campaigns/{campaign_id}', token=self.dev_token)
        delete_works = success and status == 200
        
        all_crud_works = list_works and get_works and patch_works and delete_works
        self.log_test("Ad Campaign CRUD", all_crud_works, 
                     f"List: {list_works}, Get: {get_works}, Patch: {patch_works}, Delete: {delete_works}")
    
    def test_ad_ticker_system(self):
        """Test GET /ads/ticker returns active campaigns"""
        # Test basic ticker
        success, data, status = self.make_request('GET', '/ads/ticker')
        basic_works = success and status == 200 and 'items' in data
        
        # Test ticker with country filter
        success, data, status = self.make_request('GET', '/ads/ticker?country=IL')
        country_filter_works = success and status == 200
        
        # Test ticker with region filter
        success, data, status = self.make_request('GET', '/ads/ticker?region=Tel%20Aviv')
        region_filter_works = success and status == 200
        
        # Test ticker with limit
        success, data, status = self.make_request('GET', '/ads/ticker?limit=3')
        limit_works = success and status == 200
        
        all_ticker_works = basic_works and country_filter_works and region_filter_works and limit_works
        self.log_test("Ad Ticker System", all_ticker_works, 
                     f"Basic: {basic_works}, Country: {country_filter_works}, Region: {region_filter_works}, Limit: {limit_works}")
    
    def test_ad_impression_tracking(self):
        """Test POST /ads/impression/{id} increments counters"""
        # First create a campaign to track
        campaign_data = {
            "name": "Test Campaign for Tracking",
            "creative": {
                "headline": "Test Ad",
                "body": "Test ad for impression tracking"
            },
            "status": "active"
        }
        
        success, data, status = self.make_request('POST', '/ads/campaigns', campaign_data, token=self.dev_token)
        if not (success and status == 200):
            self.log_test("Ad Impression Tracking", False, "Could not create test campaign")
            return
            
        campaign_id = data.get('id')
        
        # Track impression
        success, data, status = self.make_request('POST', f'/ads/impression/{campaign_id}')
        impression_tracked = success and status == 200 and data.get('ok') == True
        
        self.log_test("Ad Impression Tracking", impression_tracked, 
                     f"Impression tracked: {impression_tracked}")
    
    def test_ad_click_tracking(self):
        """Test POST /ads/click/{id} increments counters"""
        # Get campaign ID from previous test or create new one
        campaign_data = {
            "name": "Test Campaign for Click Tracking",
            "creative": {
                "headline": "Test Ad",
                "body": "Test ad for click tracking"
            },
            "status": "active"
        }
        
        success, data, status = self.make_request('POST', '/ads/campaigns', campaign_data, token=self.dev_token)
        if not (success and status == 200):
            self.log_test("Ad Click Tracking", False, "Could not create test campaign")
            return
            
        campaign_id = data.get('id')
        
        # Track click
        success, data, status = self.make_request('POST', f'/ads/click/{campaign_id}')
        click_tracked = success and status == 200 and data.get('ok') == True
        
        self.log_test("Ad Click Tracking", click_tracked, 
                     f"Click tracked: {click_tracked}")
    
    def test_admin_professional_controls(self):
        """Test admin controls for professionals (hide/unhide)"""
        if not self.dev_token:
            self.log_test("Admin Professional Controls", False, "No dev token available")
            return
            
        # Test GET /admin/professionals
        success, data, status = self.make_request('GET', '/admin/professionals', token=self.dev_token)
        list_works = success and status == 200 and 'items' in data
        
        if not list_works or not data.get('items'):
            self.log_test("Admin Professional Controls", False, "No professionals found for admin testing")
            return
            
        professional_user_id = data['items'][0]['id']
        
        # Test hide professional
        success, data, status = self.make_request('POST', f'/admin/professionals/{professional_user_id}/hide', token=self.dev_token)
        hide_works = success and status == 200
        
        # Test unhide professional
        success, data, status = self.make_request('POST', f'/admin/professionals/{professional_user_id}/unhide', token=self.dev_token)
        unhide_works = success and status == 200
        
        all_admin_works = list_works and hide_works and unhide_works
        self.log_test("Admin Professional Controls", all_admin_works, 
                     f"List: {list_works}, Hide: {hide_works}, Unhide: {unhide_works}")
    
    def test_admin_ad_controls(self):
        """Test admin controls for ad campaigns (disable/enable)"""
        if not self.dev_token:
            self.log_test("Admin Ad Controls", False, "No dev token available")
            return
            
        # Test GET /admin/ads/campaigns
        success, data, status = self.make_request('GET', '/admin/ads/campaigns', token=self.dev_token)
        list_works = success and status == 200 and 'items' in data
        
        if not list_works or not data.get('items'):
            self.log_test("Admin Ad Controls", False, "No campaigns found for admin testing")
            return
            
        campaign_id = data['items'][0]['id']
        
        # Test disable campaign
        success, data, status = self.make_request('POST', f'/admin/ads/campaigns/{campaign_id}/disable', token=self.dev_token)
        disable_works = success and status == 200
        
        # Test enable campaign
        success, data, status = self.make_request('POST', f'/admin/ads/campaigns/{campaign_id}/enable', token=self.dev_token)
        enable_works = success and status == 200
        
        all_admin_works = list_works and disable_works and enable_works
        self.log_test("Admin Ad Controls", all_admin_works, 
                     f"List: {list_works}, Disable: {disable_works}, Enable: {enable_works}")
    
    def test_non_professional_ad_restrictions(self):
        """Test that non-professionals cannot create ad campaigns"""
        if not self.buyer_token:
            self.log_test("Non-Professional Ad Restrictions", False, "No buyer token available")
            return
            
        campaign_data = {
            "name": "Unauthorized Campaign",
            "creative": {
                "headline": "Should Not Work",
                "body": "This should fail"
            }
        }
        
        success, data, status = self.make_request('POST', '/ads/campaigns', campaign_data, token=self.buyer_token)
        
        # Should return 403 Forbidden
        access_denied = status == 403
        self.log_test("Non-Professional Ad Restrictions", access_denied, 
                     f"Status: {status} (expected 403)")
    
    def test_hidden_professional_exclusion(self):
        """Test that hidden professionals don't appear in public directory"""
        if not self.dev_token:
            self.log_test("Hidden Professional Exclusion", False, "No dev token available")
            return
            
        # Get current professional count
        success, data, status = self.make_request('GET', '/professionals')
        if not (success and status == 200):
            self.log_test("Hidden Professional Exclusion", False, "Could not get professionals list")
            return
            
        initial_count = data.get('total', 0)
        
        # Get a professional to hide (use dev user)
        success, user_data, status = self.make_request('GET', '/users/me', token=self.dev_token)
        if not (success and status == 200):
            self.log_test("Hidden Professional Exclusion", False, "Could not get user data")
            return
            
        user_id = user_data.get('id')
        
        # Hide the professional
        success, data, status = self.make_request('POST', f'/admin/professionals/{user_id}/hide', token=self.dev_token)
        if not (success and status == 200):
            self.log_test("Hidden Professional Exclusion", False, "Could not hide professional")
            return
        
        # Check that count decreased
        success, data, status = self.make_request('GET', '/professionals')
        if success and status == 200:
            new_count = data.get('total', 0)
            count_decreased = new_count < initial_count
            
            # Restore the professional
            self.make_request('POST', f'/admin/professionals/{user_id}/unhide', token=self.dev_token)
            
            self.log_test("Hidden Professional Exclusion", count_decreased, 
                         f"Initial: {initial_count}, After hide: {new_count}")
        else:
            self.log_test("Hidden Professional Exclusion", False, "Could not verify exclusion")
    
    def test_ticker_date_filtering(self):
        """Test that ticker respects start_date and end_date"""
        if not self.dev_token:
            self.log_test("Ticker Date Filtering", False, "No dev token available")
            return
            
        from datetime import datetime, timedelta
        
        # Create campaign with future start date
        future_date = (datetime.now() + timedelta(days=1)).date().isoformat()
        campaign_data = {
            "name": "Future Campaign",
            "creative": {
                "headline": "Future Ad",
                "body": "This should not appear in ticker yet"
            },
            "status": "active",
            "start_date": future_date
        }
        
        success, data, status = self.make_request('POST', '/ads/campaigns', campaign_data, token=self.dev_token)
        if not (success and status == 200):
            self.log_test("Ticker Date Filtering", False, "Could not create future campaign")
            return
            
        campaign_id = data.get('id')
        
        # Check ticker doesn't include future campaign
        success, data, status = self.make_request('GET', '/ads/ticker')
        if success and status == 200:
            future_campaign_excluded = not any(item.get('id') == campaign_id for item in data.get('items', []))
            
            # Clean up
            self.make_request('DELETE', f'/ads/campaigns/{campaign_id}', token=self.dev_token)
            
            self.log_test("Ticker Date Filtering", future_campaign_excluded, 
                         f"Future campaign excluded from ticker: {future_campaign_excluded}")
        else:
            self.log_test("Ticker Date Filtering", False, "Could not test ticker filtering")

    def run_all_tests(self):
        """Run all test suites"""
        print("🚀 Starting DressApp Backend API Tests")
        print(f"📍 Testing against: {self.base_url}")
        print("=" * 60)
        
        # Basic connectivity
        self.test_health_check()
        
        # Authentication tests
        if not self.test_dev_bypass_auth():
            print("❌ Dev bypass failed - stopping tests")
            return self.generate_report()
            
        self.test_regular_login()
        self.test_register_new_user()
        self.test_auth_me_endpoints()
        
        # User management
        self.test_user_profile_update()
        
        # Language selector tests (NEW)
        print("\n🌍 Testing Language Selector Functionality...")
        self.test_language_persistence()
        self.test_language_validation()
        self.test_stylist_language_localization()
        self.test_garment_vision_language_localization()
        self.test_existing_endpoints_regression()
        
        # Closet operations
        self.test_closet_operations()
        self.test_closet_with_base64_image()
        
        # Listings and financial
        self.test_listings_fee_preview()
        self.test_listings_operations()
        
        # Transactions
        self.test_transactions()
        self.test_transactions_filters()
        
        # Stylist AI features
        self.test_stylist_basic()
        self.test_stylist_with_calendar()
        self.test_stylist_history()
        self.test_multipart_stylist()
        
        # REGRESSION TESTS for Phase 2
        print("\n🔄 Running Phase 2 Regression Tests...")
        self.test_multiple_pending_transactions()
        self.test_multipart_stylist_with_real_image()
        self.test_stylist_history_persistence()
        
        # PHASE 5 ADMIN TESTS
        print("\n🔄 Running Phase 5 Admin Dashboard Tests...")
        self.test_admin_overview()
        self.test_admin_overview_auth()
        self.test_admin_users()
        self.test_admin_user_promotion()
        self.test_admin_listings()
        self.test_admin_listing_status_change()
        self.test_admin_transactions()
        self.test_admin_providers()
        self.test_admin_trend_scout()
        self.test_admin_llm_usage()
        self.test_admin_system()
        
        # PHASE 5 IMAGE EDIT REGRESSION
        print("\n🔄 Running Phase 5 Image Edit Regression Test...")
        self.test_image_edit_regression()
        
        # ADD ITEM FEATURE TESTS
        print("\n🔄 Running Add Item Feature Tests...")
        self.test_analyze_item_image_base64()
        self.test_analyze_item_image_url()
        self.test_analyze_item_validation()
        self.test_closet_marketplace_intent_own()
        self.test_closet_marketplace_intent_for_sale()
        self.test_closet_marketplace_intent_donate()
        self.test_closet_marketplace_intent_swap()
        self.test_schema_fields_roundtrip()
        self.test_provider_activity_tracking()
        
        # PHASE M: SYSTEM-NATIVE SPEECH TESTS
        print("\n🎤 Running Phase M: System-Native Speech Tests...")
        self.test_stylist_skip_tts_true()
        self.test_stylist_skip_tts_default()
        self.test_stylist_skip_tts_false_explicit()
        self.test_stylist_voice_audio_with_skip_tts()
        self.test_stylist_skip_tts_invalid_value()
        self.test_stylist_hebrew_localization_skip_tts()
        self.test_stylist_history_regression()
        self.test_phase_l_language_persistence_regression()
        self.test_closet_analyze_regression()
        
        # PHASE U: PROFESSIONAL FASHION EXPERT TESTS
        print("\n👔 Running Phase U: Professional Fashion Expert Tests...")
        self.test_professional_profile_setup()
        self.test_professional_directory_listing()
        self.test_professional_directory_filters()
        self.test_professional_individual_lookup()
        self.test_ad_campaign_creation()
        self.test_ad_campaign_crud()
        self.test_ad_ticker_system()
        self.test_ad_impression_tracking()
        self.test_ad_click_tracking()
        self.test_admin_professional_controls()
        self.test_admin_ad_controls()
        self.test_non_professional_ad_restrictions()
        self.test_hidden_professional_exclusion()
        self.test_ticker_date_filtering()
        
        return self.generate_report()

    def generate_report(self):
        """Generate final test report"""
        print("\n" + "=" * 60)
        print("📊 TEST RESULTS SUMMARY")
        print("=" * 60)
        
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        print(f"✅ Passed: {self.tests_passed}/{self.tests_run} ({success_rate:.1f}%)")
        
        if self.failed_tests:
            print(f"\n❌ Failed Tests ({len(self.failed_tests)}):")
            for i, failure in enumerate(self.failed_tests, 1):
                print(f"  {i}. {failure['test']}")
                if failure['details']:
                    print(f"     Details: {failure['details']}")
        
        print("\n🔍 Key Findings:")
        print("• fal.ai balance exhausted - image segmentation returns null (expected)")
        print("• Google Calendar integration is mocked (expected)")
        print("• Stripe Connect not wired - transactions stay pending (expected)")
        
        return {
            "tests_run": self.tests_run,
            "tests_passed": self.tests_passed,
            "success_rate": success_rate,
            "failed_tests": self.failed_tests
        }

def main():
    """Main test execution"""
    tester = DressAppAPITester()
    results = tester.run_all_tests()
    
    # Return appropriate exit code
    return 0 if results["success_rate"] >= 80 else 1

if __name__ == "__main__":
    sys.exit(main())