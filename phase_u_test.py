#!/usr/bin/env python3
"""
Phase U Professional Fashion Expert Tests
Focused testing of professional features only
"""

import requests
import sys
import json
from datetime import datetime, timedelta

class PhaseUTester:
    def __init__(self, base_url: str = "https://ai-stylist-api.preview.emergentagent.com"):
        self.base_url = base_url.rstrip('/')
        self.dev_token = None
        self.buyer_token = None
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

    def make_request(self, method: str, endpoint: str, data=None, token: str = None) -> tuple[bool, dict, int]:
        """Make HTTP request with error handling"""
        url = f"{self.base_url}/api/v1{endpoint}"
        headers = {'Content-Type': 'application/json'}
        
        if token:
            headers['Authorization'] = f'Bearer {token}'

        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=30)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=30)
            elif method == 'PATCH':
                response = requests.patch(url, json=data, headers=headers, timeout=30)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=30)
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
        """Setup authentication tokens"""
        # Get dev token
        success, data, status = self.make_request('POST', '/auth/dev-bypass')
        if success and status == 200 and 'access_token' in data:
            self.dev_token = data['access_token']
            print("✅ Dev auth setup")
        else:
            print("❌ Dev auth failed")
            return False

        # Register buyer user
        import time
        timestamp = int(time.time())
        register_data = {
            "email": f"buyer{timestamp}@dressapp.io",
            "password": "BuyerPass123!",
            "display_name": f"Test Buyer {timestamp}"
        }
        
        success, data, status = self.make_request('POST', '/auth/register', register_data)
        if success and status == 201 and 'access_token' in data:
            self.buyer_token = data['access_token']
            print("✅ Buyer auth setup")
        else:
            print("❌ Buyer auth failed")
            
        return True

    def test_professional_profile_setup(self):
        """Test PATCH /users/me with professional fields"""
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
        """Test GET /professionals with filters"""
        filters = [
            ('country=IL', 'Country filter'),
            ('profession=Fashion%20Stylist', 'Profession filter'),
            ('q=style', 'Text search'),
            ('region=Tel%20Aviv', 'Region filter')
        ]
        
        all_work = True
        failed_filters = []
        
        for filter_param, filter_name in filters:
            success, data, status = self.make_request('GET', f'/professionals?{filter_param}')
            if not (success and status == 200):
                all_work = False
                failed_filters.append(filter_name)
        
        self.log_test("Professional Directory Filters", all_work, 
                     f"Failed filters: {failed_filters}" if failed_filters else "All filters working")

    def test_ad_campaign_creation(self):
        """Test POST /ads/campaigns creates campaign for professionals only"""
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
            
            self.test_campaign_id = data.get('id')
        else:
            self.log_test("Ad Campaign Creation", False, f"Status: {status}, Data: {data}")

    def test_non_professional_ad_restrictions(self):
        """Test that non-professionals cannot create ad campaigns"""
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

    def test_ad_ticker_system(self):
        """Test GET /ads/ticker returns active campaigns"""
        endpoints = [
            '/ads/ticker',
            '/ads/ticker?country=IL',
            '/ads/ticker?region=Tel%20Aviv',
            '/ads/ticker?limit=3'
        ]
        
        all_work = True
        for endpoint in endpoints:
            success, data, status = self.make_request('GET', endpoint)
            if not (success and status == 200 and 'items' in data):
                all_work = False
                break
        
        self.log_test("Ad Ticker System", all_work, 
                     f"All ticker endpoints working: {all_work}")

    def test_impression_click_tracking(self):
        """Test impression and click tracking"""
        if not hasattr(self, 'test_campaign_id'):
            self.log_test("Impression Click Tracking", False, "No campaign ID available")
            return
            
        # Test impression tracking
        success, data, status = self.make_request('POST', f'/ads/impression/{self.test_campaign_id}')
        impression_works = success and status == 200 and data.get('ok') == True
        
        # Test click tracking
        success, data, status = self.make_request('POST', f'/ads/click/{self.test_campaign_id}')
        click_works = success and status == 200 and data.get('ok') == True
        
        both_work = impression_works and click_works
        self.log_test("Impression Click Tracking", both_work, 
                     f"Impression: {impression_works}, Click: {click_works}")

    def test_admin_controls(self):
        """Test admin controls for professionals and ads"""
        # Test professional admin controls
        success, data, status = self.make_request('GET', '/admin/professionals', token=self.dev_token)
        prof_admin_works = success and status == 200 and 'items' in data
        
        # Test ad admin controls
        success, data, status = self.make_request('GET', '/admin/ads/campaigns', token=self.dev_token)
        ad_admin_works = success and status == 200 and 'items' in data
        
        both_work = prof_admin_works and ad_admin_works
        self.log_test("Admin Controls", both_work, 
                     f"Professional admin: {prof_admin_works}, Ad admin: {ad_admin_works}")

    def run_all_tests(self):
        """Run all Phase U tests"""
        print("🚀 Starting Phase U Professional Fashion Expert Tests")
        print(f"📍 Testing against: {self.base_url}")
        print("=" * 60)
        
        if not self.setup_auth():
            return self.generate_report()
        
        print("\n👔 Running Phase U Tests...")
        self.test_professional_profile_setup()
        self.test_professional_directory_listing()
        self.test_professional_directory_filters()
        self.test_ad_campaign_creation()
        self.test_non_professional_ad_restrictions()
        self.test_ad_ticker_system()
        self.test_impression_click_tracking()
        self.test_admin_controls()
        
        return self.generate_report()

    def generate_report(self):
        """Generate final test report"""
        print("\n" + "=" * 60)
        print("📊 PHASE U TEST RESULTS")
        print("=" * 60)
        
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        print(f"✅ Passed: {self.tests_passed}/{self.tests_run} ({success_rate:.1f}%)")
        
        if self.failed_tests:
            print(f"\n❌ Failed Tests ({len(self.failed_tests)}):")
            for i, failure in enumerate(self.failed_tests, 1):
                print(f"  {i}. {failure['test']}")
                if failure['details']:
                    print(f"     Details: {failure['details']}")
        
        return {
            "tests_run": self.tests_run,
            "tests_passed": self.tests_passed,
            "success_rate": success_rate,
            "failed_tests": self.failed_tests
        }

def main():
    """Main test execution"""
    tester = PhaseUTester()
    results = tester.run_all_tests()
    
    # Return appropriate exit code
    return 0 if results["success_rate"] >= 90 else 1

if __name__ == "__main__":
    sys.exit(main())