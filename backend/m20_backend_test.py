#!/usr/bin/env python3
"""
M20 Patch Backend Testing
Tests the three M20 fixes:
1. BUG FIX - thumbnail_data_url explicitly set to None (not $unset)
2. FEATURE - Cross-page analyze progress tracking
3. FEATURE - Global polish progress + batch done toast
"""

import requests
import json
import time
import sys
import base64
from datetime import datetime
from typing import Dict, Any

# Simple 1x1 pixel JPEG for testing
TEST_IMAGE_JPEG = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\xff\xc0\x00\x11\x08\x00\x01\x00\x01\x01\x01\x11\x00\x02\x11\x01\x03\x11\x01\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x08\xff\xc4\x00\x14\x10\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00\x3f\x00\xaa\xff\xd9'

class M20BackendTester:
    def __init__(self, base_url: str = "https://ai-stylist-api.preview.emergentagent.com"):
        self.base_url = base_url
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []

    def log_result(self, test_name: str, success: bool, details: str = ""):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {test_name}: PASSED")
        else:
            print(f"❌ {test_name}: FAILED - {details}")
        
        if details:
            print(f"   Details: {details}")
        
        self.test_results.append({
            "test": test_name,
            "success": success,
            "details": details,
            "timestamp": datetime.now().isoformat()
        })

    def get_auth_token(self) -> bool:
        """Get JWT token using dev-bypass"""
        print("\n🔐 Getting auth token...")
        try:
            response = requests.post(f"{self.base_url}/api/v1/auth/dev-bypass", timeout=10)
            if response.status_code == 200:
                data = response.json()
                self.token = data.get("access_token")
                self.log_result("Auth Token Acquisition", True, f"Token obtained")
                return True
            else:
                self.log_result("Auth Token Acquisition", False, f"Status: {response.status_code}")
                return False
        except Exception as e:
            self.log_result("Auth Token Acquisition", False, str(e))
            return False

    def test_p0_create_item_with_defer_matte(self) -> bool:
        """
        BACKEND P0: POST /api/v1/closet with defer_matte=true creates item 
        with clean_image_status='pending'
        """
        print("\n🧪 Testing P0: Create item with defer_matte=true...")
        try:
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            }
            
            # Create item with defer_matte=true
            image_b64 = base64.b64encode(TEST_IMAGE_JPEG).decode('ascii')
            payload = {
                "title": "M20 Test Item - Defer Matte",
                "category": "Top",
                "image_base64": image_b64,
                "defer_matte": True,
                "marketplace_intent": "own"
            }
            
            response = requests.post(
                f"{self.base_url}/api/v1/closet",
                json=payload,
                headers=headers,
                timeout=30
            )
            
            if response.status_code != 201:
                self.log_result("P0: Create Item with defer_matte", False, 
                              f"Status: {response.status_code}, Body: {response.text[:200]}")
                return False
            
            item = response.json()
            item_id = item.get("id")
            clean_image_status = item.get("clean_image_status")
            
            if clean_image_status != "pending":
                self.log_result("P0: Create Item with defer_matte", False, 
                              f"Expected clean_image_status='pending', got '{clean_image_status}'")
                return False
            
            self.log_result("P0: Create Item with defer_matte", True, 
                          f"Item created with id={item_id}, clean_image_status='pending'")
            
            # Store item_id for next test
            self.pending_item_id = item_id
            return True
            
        except Exception as e:
            self.log_result("P0: Create Item with defer_matte", False, str(e))
            return False

    def test_p0_background_matte_completion(self) -> bool:
        """
        BACKEND P0: After BackgroundTask completes, GET /api/v1/closet/{id} 
        returns clean_image_status='ready' AND thumbnail_data_url=null (explicitly null)
        """
        print("\n🧪 Testing P0: Background matte completion...")
        
        if not hasattr(self, 'pending_item_id'):
            self.log_result("P0: Background Matte Completion", False, 
                          "No pending_item_id from previous test")
            return False
        
        try:
            headers = {"Authorization": f"Bearer {self.token}"}
            
            # Poll for up to 30 seconds (background matte typically takes 5-20s)
            max_attempts = 15
            poll_interval = 2
            
            print(f"   Polling item {self.pending_item_id} for up to {max_attempts * poll_interval}s...")
            
            for attempt in range(max_attempts):
                response = requests.get(
                    f"{self.base_url}/api/v1/closet/{self.pending_item_id}",
                    headers=headers,
                    timeout=10
                )
                
                if response.status_code != 200:
                    self.log_result("P0: Background Matte Completion", False, 
                                  f"GET failed with status: {response.status_code}")
                    return False
                
                item = response.json()
                clean_image_status = item.get("clean_image_status")
                
                print(f"   Attempt {attempt + 1}/{max_attempts}: clean_image_status='{clean_image_status}'")
                
                if clean_image_status == "ready":
                    # Check that thumbnail_data_url is explicitly null (not missing)
                    has_thumbnail_key = "thumbnail_data_url" in item
                    thumbnail_value = item.get("thumbnail_data_url")
                    
                    if not has_thumbnail_key:
                        self.log_result("P0: Background Matte Completion", False, 
                                      "thumbnail_data_url key is MISSING from response (should be explicitly null)")
                        return False
                    
                    if thumbnail_value is not None:
                        self.log_result("P0: Background Matte Completion", False, 
                                      f"thumbnail_data_url is '{thumbnail_value}' (should be null)")
                        return False
                    
                    # Check that clean_image_url is populated
                    clean_image_url = item.get("clean_image_url")
                    if not clean_image_url:
                        self.log_result("P0: Background Matte Completion", False, 
                                      "clean_image_url is not populated")
                        return False
                    
                    self.log_result("P0: Background Matte Completion", True, 
                                  f"Status='ready', thumbnail_data_url=null (explicit), clean_image_url populated")
                    return True
                
                elif clean_image_status == "failed":
                    self.log_result("P0: Background Matte Completion", False, 
                                  "Background matte failed")
                    return False
                
                # Still pending, wait and retry
                time.sleep(poll_interval)
            
            # Timeout
            self.log_result("P0: Background Matte Completion", False, 
                          f"Timeout after {max_attempts * poll_interval}s - status still '{clean_image_status}'")
            return False
            
        except Exception as e:
            self.log_result("P0: Background Matte Completion", False, str(e))
            return False

    def test_p0_analyze_no_regression(self) -> bool:
        """
        BACKEND P0: POST /api/v1/closet/analyze still works (no regression from M19)
        """
        print("\n🧪 Testing P0: Analyze endpoint no regression...")
        try:
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            }
            
            image_b64 = base64.b64encode(TEST_IMAGE_JPEG).decode('ascii')
            payload = {
                "image_base64": image_b64,
                "multi": True
            }
            
            response = requests.post(
                f"{self.base_url}/api/v1/closet/analyze",
                json=payload,
                headers=headers,
                timeout=60
            )
            
            if response.status_code != 200:
                self.log_result("P0: Analyze No Regression", False, 
                              f"Status: {response.status_code}, Body: {response.text[:200]}")
                return False
            
            result = response.json()
            
            # Check for expected fields
            if "items" not in result:
                self.log_result("P0: Analyze No Regression", False, 
                              "Response missing 'items' field")
                return False
            
            items = result.get("items", [])
            count = result.get("count", 0)
            
            self.log_result("P0: Analyze No Regression", True, 
                          f"Analyze returned {count} items")
            return True
            
        except Exception as e:
            self.log_result("P0: Analyze No Regression", False, str(e))
            return False

    def test_p1_closet_list(self) -> bool:
        """
        BACKEND P1: GET /api/v1/closet returns items list including any with clean_image_status
        """
        print("\n🧪 Testing P1: Closet list endpoint...")
        try:
            headers = {"Authorization": f"Bearer {self.token}"}
            
            response = requests.get(
                f"{self.base_url}/api/v1/closet",
                headers=headers,
                timeout=10
            )
            
            if response.status_code != 200:
                self.log_result("P1: Closet List", False, 
                              f"Status: {response.status_code}")
                return False
            
            result = response.json()
            items = result.get("items", [])
            total = result.get("total", 0)
            
            # Check if any items have clean_image_status field
            items_with_status = [item for item in items if "clean_image_status" in item]
            
            self.log_result("P1: Closet List", True, 
                          f"Returned {len(items)} items (total={total}), "
                          f"{len(items_with_status)} with clean_image_status")
            return True
            
        except Exception as e:
            self.log_result("P1: Closet List", False, str(e))
            return False

    def run_all_tests(self) -> Dict[str, Any]:
        """Run all tests and return summary"""
        print("🧪 Starting M20 Patch Backend Tests...")
        print(f"🔗 Testing against: {self.base_url}")
        print("=" * 70)
        
        # Get auth token first
        if not self.get_auth_token():
            return self.get_summary()
        
        # Run tests in order (some depend on previous ones)
        test_methods = [
            self.test_p0_create_item_with_defer_matte,
            self.test_p0_background_matte_completion,
            self.test_p0_analyze_no_regression,
            self.test_p1_closet_list,
        ]
        
        for test_method in test_methods:
            try:
                test_method()
            except Exception as e:
                print(f"❌ {test_method.__name__}: EXCEPTION - {str(e)}")
                self.tests_run += 1
            
            # Small delay between tests
            time.sleep(0.5)
        
        return self.get_summary()

    def get_summary(self) -> Dict[str, Any]:
        """Get test summary"""
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        
        print("\n" + "=" * 70)
        print(f"📊 Test Summary: {self.tests_passed}/{self.tests_run} passed ({success_rate:.1f}%)")
        
        if self.tests_passed == self.tests_run:
            print("🎉 All backend tests passed!")
        else:
            print("⚠️  Some tests failed - check details above")
        
        return {
            "total_tests": self.tests_run,
            "passed_tests": self.tests_passed,
            "failed_tests": self.tests_run - self.tests_passed,
            "success_rate": success_rate,
            "test_results": self.test_results,
            "timestamp": datetime.now().isoformat()
        }

def main():
    """Main test runner"""
    tester = M20BackendTester()
    summary = tester.run_all_tests()
    
    # Save results to file
    with open("/tmp/m20_backend_test_results.json", "w") as f:
        json.dump(summary, f, indent=2)
    
    print(f"\n📄 Results saved to /tmp/m20_backend_test_results.json")
    
    # Exit with appropriate code
    sys.exit(0 if summary["passed_tests"] == summary["total_tests"] else 1)

if __name__ == "__main__":
    main()
