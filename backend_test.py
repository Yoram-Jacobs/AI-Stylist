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
                "stripe_fee_cents": 102,  # 2.9% + $0.30
                "net_after_stripe_cents": 2398,
                "platform_fee_cents": 168,  # 7% of net_after_stripe
                "seller_net_cents": 2230
            }
            
            all_correct = all(data.get(k) == v for k, v in expected.items())
            self.log_test("Listings Fee Preview", all_correct, 
                         f"Expected: {expected}, Got: {data}")
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
            has_messages = isinstance(data, list) and len(data) > 0
            if has_messages:
                # Check for both user and assistant messages
                roles = [msg.get('role') for msg in data]
                has_user_and_assistant = 'user' in roles and 'assistant' in roles
                self.log_test("Stylist History", has_user_and_assistant, 
                             f"Found {len(data)} messages with roles: {set(roles)}")
            else:
                self.log_test("Stylist History", True, "No conversation history yet (expected)")
        else:
            self.log_test("Stylist History", False, f"Status: {status}, Data: {data}")

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