#!/usr/bin/env python3
"""
Phase U Edge Case Tests
Testing specific edge cases mentioned in the review request
"""

import requests
import sys
import json
from datetime import datetime, timedelta

class PhaseUEdgeCaseTester:
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
        success, data, status = self.make_request('POST', '/auth/dev-bypass')
        if success and status == 200 and 'access_token' in data:
            self.dev_token = data['access_token']
            return True
        return False

    def test_hidden_professional_404(self):
        """Test GET /professionals/{id} returns 404 for hidden professionals"""
        # First get a professional ID
        success, data, status = self.make_request('GET', '/professionals')
        if not (success and status == 200 and data.get('items')):
            self.log_test("Hidden Professional 404", False, "No professionals found")
            return
            
        professional_id = data['items'][0]['id']
        
        # Hide the professional
        success, data, status = self.make_request('POST', f'/admin/professionals/{professional_id}/hide', token=self.dev_token)
        if not (success and status == 200):
            self.log_test("Hidden Professional 404", False, "Could not hide professional")
            return
        
        # Try to access the hidden professional
        success, data, status = self.make_request('GET', f'/professionals/{professional_id}')
        returns_404 = status == 404
        
        # Restore the professional
        self.make_request('POST', f'/admin/professionals/{professional_id}/unhide', token=self.dev_token)
        
        self.log_test("Hidden Professional 404", returns_404, 
                     f"Status: {status} (expected 404)")

    def test_ticker_skips_disabled_campaigns(self):
        """Test ticker correctly skips disabled campaigns"""
        # Create a campaign
        campaign_data = {
            "name": "Test Campaign for Disable",
            "creative": {
                "headline": "Test Ad",
                "body": "This should be disabled"
            },
            "status": "active"
        }
        
        success, data, status = self.make_request('POST', '/ads/campaigns', campaign_data, token=self.dev_token)
        if not (success and status == 200):
            self.log_test("Ticker Skips Disabled", False, "Could not create campaign")
            return
            
        campaign_id = data.get('id')
        
        # Check ticker includes the campaign
        success, data, status = self.make_request('GET', '/ads/ticker')
        if not (success and status == 200):
            self.log_test("Ticker Skips Disabled", False, "Ticker request failed")
            return
            
        campaign_in_ticker = any(item.get('id') == campaign_id for item in data.get('items', []))
        
        # Disable the campaign
        success, data, status = self.make_request('POST', f'/admin/ads/campaigns/{campaign_id}/disable', token=self.dev_token)
        if not (success and status == 200):
            self.log_test("Ticker Skips Disabled", False, "Could not disable campaign")
            return
        
        # Check ticker excludes the disabled campaign
        success, data, status = self.make_request('GET', '/ads/ticker')
        if success and status == 200:
            campaign_excluded = not any(item.get('id') == campaign_id for item in data.get('items', []))
            
            # Clean up
            self.make_request('DELETE', f'/ads/campaigns/{campaign_id}', token=self.dev_token)
            
            self.log_test("Ticker Skips Disabled", campaign_excluded, 
                         f"Campaign excluded after disable: {campaign_excluded}")
        else:
            self.log_test("Ticker Skips Disabled", False, "Could not verify exclusion")

    def test_ticker_respects_date_window(self):
        """Test ticker respects start_date and end_date"""
        from datetime import datetime, timedelta
        
        # Create campaign with future start date
        future_date = (datetime.now() + timedelta(days=1)).date().isoformat()
        campaign_data = {
            "name": "Future Campaign",
            "creative": {
                "headline": "Future Ad",
                "body": "This should not appear yet"
            },
            "status": "active",
            "start_date": future_date
        }
        
        success, data, status = self.make_request('POST', '/ads/campaigns', campaign_data, token=self.dev_token)
        if not (success and status == 200):
            self.log_test("Ticker Date Window", False, "Could not create future campaign")
            return
            
        campaign_id = data.get('id')
        
        # Check ticker excludes future campaign
        success, data, status = self.make_request('GET', '/ads/ticker')
        if success and status == 200:
            future_excluded = not any(item.get('id') == campaign_id for item in data.get('items', []))
            
            # Clean up
            self.make_request('DELETE', f'/ads/campaigns/{campaign_id}', token=self.dev_token)
            
            self.log_test("Ticker Date Window", future_excluded, 
                         f"Future campaign excluded: {future_excluded}")
        else:
            self.log_test("Ticker Date Window", False, "Could not verify date filtering")

    def test_impression_tracking_increments_spent(self):
        """Test impression tracking increments spent_cents (1 per impression)"""
        # Create a campaign
        campaign_data = {
            "name": "Impression Tracking Test",
            "creative": {
                "headline": "Track Me",
                "body": "Testing impression tracking"
            },
            "status": "active"
        }
        
        success, data, status = self.make_request('POST', '/ads/campaigns', campaign_data, token=self.dev_token)
        if not (success and status == 200):
            self.log_test("Impression Increments Spent", False, "Could not create campaign")
            return
            
        campaign_id = data.get('id')
        initial_spent = data.get('spent_cents', 0)
        
        # Track impression
        success, data, status = self.make_request('POST', f'/ads/impression/{campaign_id}')
        if not (success and status == 200):
            self.log_test("Impression Increments Spent", False, "Impression tracking failed")
            return
        
        # Get updated campaign data
        success, data, status = self.make_request('GET', f'/ads/campaigns/{campaign_id}', token=self.dev_token)
        if success and status == 200:
            new_spent = data.get('spent_cents', 0)
            spent_incremented = new_spent == initial_spent + 1
            
            # Clean up
            self.make_request('DELETE', f'/ads/campaigns/{campaign_id}', token=self.dev_token)
            
            self.log_test("Impression Increments Spent", spent_incremented, 
                         f"Spent: {initial_spent} -> {new_spent} (expected +1)")
        else:
            self.log_test("Impression Increments Spent", False, "Could not verify spent increment")

    def test_click_tracking_increments_spent(self):
        """Test click tracking increments spent_cents (5 per click)"""
        # Create a campaign
        campaign_data = {
            "name": "Click Tracking Test",
            "creative": {
                "headline": "Click Me",
                "body": "Testing click tracking"
            },
            "status": "active"
        }
        
        success, data, status = self.make_request('POST', '/ads/campaigns', campaign_data, token=self.dev_token)
        if not (success and status == 200):
            self.log_test("Click Increments Spent", False, "Could not create campaign")
            return
            
        campaign_id = data.get('id')
        initial_spent = data.get('spent_cents', 0)
        
        # Track click
        success, data, status = self.make_request('POST', f'/ads/click/{campaign_id}')
        if not (success and status == 200):
            self.log_test("Click Increments Spent", False, "Click tracking failed")
            return
        
        # Get updated campaign data
        success, data, status = self.make_request('GET', f'/ads/campaigns/{campaign_id}', token=self.dev_token)
        if success and status == 200:
            new_spent = data.get('spent_cents', 0)
            spent_incremented = new_spent == initial_spent + 5
            
            # Clean up
            self.make_request('DELETE', f'/ads/campaigns/{campaign_id}', token=self.dev_token)
            
            self.log_test("Click Increments Spent", spent_incremented, 
                         f"Spent: {initial_spent} -> {new_spent} (expected +5)")
        else:
            self.log_test("Click Increments Spent", False, "Could not verify spent increment")

    def test_campaign_owner_only_access(self):
        """Test GET /ads/campaigns/{id} is owner-only (403 for non-owner)"""
        # Create a campaign with dev user
        campaign_data = {
            "name": "Owner Test Campaign",
            "creative": {
                "headline": "Owner Only",
                "body": "Testing owner access"
            },
            "status": "active"
        }
        
        success, data, status = self.make_request('POST', '/ads/campaigns', campaign_data, token=self.dev_token)
        if not (success and status == 200):
            self.log_test("Campaign Owner Only", False, "Could not create campaign")
            return
            
        campaign_id = data.get('id')
        
        # Register another user to test non-owner access
        import time
        timestamp = int(time.time())
        register_data = {
            "email": f"nonowner{timestamp}@dressapp.io",
            "password": "NonOwner123!",
            "display_name": f"Non Owner {timestamp}"
        }
        
        success, data, status = self.make_request('POST', '/auth/register', register_data)
        if not (success and status == 201):
            self.log_test("Campaign Owner Only", False, "Could not create non-owner user")
            return
            
        non_owner_token = data.get('access_token')
        
        # Try to access campaign as non-owner
        success, data, status = self.make_request('GET', f'/ads/campaigns/{campaign_id}', token=non_owner_token)
        access_denied = status == 403
        
        # Clean up
        self.make_request('DELETE', f'/ads/campaigns/{campaign_id}', token=self.dev_token)
        
        self.log_test("Campaign Owner Only", access_denied, 
                     f"Non-owner access status: {status} (expected 403)")

    def run_all_tests(self):
        """Run all edge case tests"""
        print("🚀 Starting Phase U Edge Case Tests")
        print(f"📍 Testing against: {self.base_url}")
        print("=" * 60)
        
        if not self.setup_auth():
            print("❌ Auth setup failed")
            return self.generate_report()
        
        print("\n🔍 Running Edge Case Tests...")
        self.test_hidden_professional_404()
        self.test_ticker_skips_disabled_campaigns()
        self.test_ticker_respects_date_window()
        self.test_impression_tracking_increments_spent()
        self.test_click_tracking_increments_spent()
        self.test_campaign_owner_only_access()
        
        return self.generate_report()

    def generate_report(self):
        """Generate final test report"""
        print("\n" + "=" * 60)
        print("📊 EDGE CASE TEST RESULTS")
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
    tester = PhaseUEdgeCaseTester()
    results = tester.run_all_tests()
    
    # Return appropriate exit code
    return 0 if results["success_rate"] >= 90 else 1

if __name__ == "__main__":
    sys.exit(main())