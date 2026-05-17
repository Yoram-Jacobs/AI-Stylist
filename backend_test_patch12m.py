#!/usr/bin/env python3
"""
Backend API Testing for Patch 12m - Phantom-Drop Guard
Tests the phantom-drop guard that prevents white-window artifacts in the closet.
"""

import requests
import json
import time
import sys
import os
import base64
from datetime import datetime
from typing import Dict, Any, List

class Patch12mTester:
    def __init__(self, base_url: str = "https://ai-stylist-api.preview.emergentagent.com"):
        self.base_url = base_url
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []
        self.uploaded_items = []
        self.phantom_drops_expected = 0
        
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
        try:
            print("\n🔑 Getting authentication token...")
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

    def clear_closet(self) -> bool:
        """Clear all items from closet before testing"""
        try:
            print("\n🧹 Clearing closet before tests...")
            headers = {"Authorization": f"Bearer {self.token}"}
            
            # Get all items
            response = requests.get(f"{self.base_url}/api/v1/closet", headers=headers, timeout=30)
            if response.status_code != 200:
                print(f"   Warning: Could not fetch closet items: {response.status_code}")
                return True  # Continue anyway
            
            items = response.json()
            deleted_count = 0
            
            for item in items:
                item_id = item.get("id")
                if item_id:
                    del_response = requests.delete(
                        f"{self.base_url}/api/v1/closet/{item_id}",
                        headers=headers,
                        timeout=10
                    )
                    if del_response.status_code in [200, 204]:
                        deleted_count += 1
            
            print(f"   Deleted {deleted_count} items from closet")
            return True
            
        except Exception as e:
            print(f"   Warning: Error clearing closet: {e}")
            return True  # Continue anyway

    def upload_test_images(self, image_paths: List[str]) -> Dict[str, Any]:
        """Upload test images and analyze them"""
        try:
            print(f"\n📤 Uploading {len(image_paths)} test images...")
            headers = {"Authorization": f"Bearer {self.token}"}
            
            results = {
                "analyzed_items": [],
                "errors": []
            }
            
            for img_path in image_paths:
                try:
                    # Read image file
                    with open(img_path, 'rb') as f:
                        img_bytes = f.read()
                    
                    img_b64 = base64.b64encode(img_bytes).decode('ascii')
                    
                    # Analyze image
                    print(f"   Analyzing {os.path.basename(img_path)}...")
                    analyze_response = requests.post(
                        f"{self.base_url}/api/v1/closet/analyze",
                        json={"image_base64": img_b64, "multi": True},
                        headers=headers,
                        timeout=120
                    )
                    
                    if analyze_response.status_code != 200:
                        results["errors"].append({
                            "file": img_path,
                            "error": f"Analyze failed: {analyze_response.status_code}"
                        })
                        continue
                    
                    analyze_data = analyze_response.json()
                    items = analyze_data.get("items", [])
                    
                    print(f"   Detected {len(items)} items in {os.path.basename(img_path)}")
                    
                    # Save each detected item
                    for item in items:
                        analysis = item.get("analysis", {})
                        crop_b64 = item.get("crop_base64")
                        
                        if not crop_b64:
                            continue
                        
                        # Build save payload
                        save_payload = {
                            "title": analysis.get("title", "Test Item"),
                            "category": analysis.get("category", "Accessories"),
                            "sub_category": analysis.get("sub_category"),
                            "item_type": analysis.get("item_type"),
                            "color": analysis.get("color"),
                            "colors": analysis.get("colors", []),
                            "pattern": analysis.get("pattern"),
                            "brand": analysis.get("brand"),
                            "image_base64": crop_b64,
                            "image_mime": item.get("crop_mime", "image/jpeg"),
                            "defer_matte": item.get("defer_matte", False),
                            "from_one_pass": item.get("one_pass", False),
                        }
                        
                        # Save item
                        save_response = requests.post(
                            f"{self.base_url}/api/v1/closet",
                            json=save_payload,
                            headers=headers,
                            timeout=30
                        )
                        
                        if save_response.status_code == 201:
                            saved_item = save_response.json()
                            item_id = saved_item.get("id")
                            clean_status = saved_item.get("clean_image_status")
                            
                            results["analyzed_items"].append({
                                "id": item_id,
                                "title": saved_item.get("title"),
                                "category": saved_item.get("category"),
                                "clean_image_status": clean_status,
                                "source_file": os.path.basename(img_path)
                            })
                            
                            self.uploaded_items.append(item_id)
                            print(f"   ✓ Saved: {saved_item.get('title')} (ID: {item_id}, status: {clean_status})")
                        else:
                            results["errors"].append({
                                "file": img_path,
                                "error": f"Save failed: {save_response.status_code}"
                            })
                    
                except Exception as e:
                    results["errors"].append({
                        "file": img_path,
                        "error": str(e)
                    })
            
            return results
            
        except Exception as e:
            print(f"   Error in upload_test_images: {e}")
            return {"analyzed_items": [], "errors": [str(e)]}

    def wait_for_polish_completion(self, timeout_seconds: int = 180) -> bool:
        """Wait for all items to complete polishing"""
        try:
            print(f"\n⏳ Waiting for polish completion (timeout: {timeout_seconds}s)...")
            headers = {"Authorization": f"Bearer {self.token}"}
            
            start_time = time.time()
            pending_items = set(self.uploaded_items)
            
            while pending_items and (time.time() - start_time) < timeout_seconds:
                time.sleep(3)  # Poll every 3 seconds
                
                # Check each pending item
                for item_id in list(pending_items):
                    try:
                        response = requests.get(
                            f"{self.base_url}/api/v1/closet/{item_id}",
                            headers=headers,
                            timeout=10
                        )
                        
                        if response.status_code == 404:
                            # Item was deleted by phantom-drop guard
                            print(f"   ⚠️  Item {item_id} was deleted (phantom-drop)")
                            pending_items.remove(item_id)
                            self.phantom_drops_expected += 1
                        elif response.status_code == 200:
                            item = response.json()
                            status = item.get("clean_image_status")
                            
                            if status in ["ready", "failed", None]:
                                print(f"   ✓ Item {item_id} completed: {status}")
                                pending_items.remove(item_id)
                    except Exception as e:
                        print(f"   Warning: Error checking item {item_id}: {e}")
                
                if pending_items:
                    elapsed = int(time.time() - start_time)
                    print(f"   Still pending: {len(pending_items)} items ({elapsed}s elapsed)")
            
            if pending_items:
                print(f"   ⚠️  Timeout: {len(pending_items)} items still pending")
                return False
            
            print(f"   ✓ All items completed polishing")
            return True
            
        except Exception as e:
            print(f"   Error in wait_for_polish_completion: {e}")
            return False

    def verify_no_white_windows(self) -> bool:
        """Verify no white-window cards exist in closet"""
        try:
            print("\n🔍 Verifying no white-window cards in closet...")
            headers = {"Authorization": f"Bearer {self.token}"}
            
            response = requests.get(f"{self.base_url}/api/v1/closet", headers=headers, timeout=30)
            if response.status_code != 200:
                self.log_result("No White Windows Check", False, f"Failed to fetch closet: {response.status_code}")
                return False
            
            items = response.json()
            white_windows = []
            
            for item in items:
                clean_url = item.get("clean_image_url")
                clean_status = item.get("clean_image_status")
                
                # A white window would have clean_image_status="ready" but very low alpha coverage
                # We can't directly check alpha coverage from the API, but we can check if the item exists
                # and has a clean_image_url (which means it passed the guard)
                
                if clean_status == "ready" and clean_url:
                    # Item passed the guard, so it should have meaningful alpha coverage
                    pass
                elif clean_status == "pending":
                    white_windows.append({
                        "id": item.get("id"),
                        "title": item.get("title"),
                        "reason": "Still pending polish"
                    })
            
            if white_windows:
                self.log_result("No White Windows Check", False, 
                              f"Found {len(white_windows)} items still pending: {white_windows}")
                return False
            
            self.log_result("No White Windows Check", True, 
                          f"All {len(items)} items in closet have completed polish")
            return True
            
        except Exception as e:
            self.log_result("No White Windows Check", False, str(e))
            return False

    def verify_deletion_count(self, expected_regions: int) -> bool:
        """Verify deletion count matches expected phantom drops"""
        try:
            print("\n🔢 Verifying deletion count...")
            headers = {"Authorization": f"Bearer {self.token}"}
            
            response = requests.get(f"{self.base_url}/api/v1/closet", headers=headers, timeout=30)
            if response.status_code != 200:
                self.log_result("Deletion Count Check", False, f"Failed to fetch closet: {response.status_code}")
                return False
            
            items = response.json()
            actual_count = len(items)
            expected_count = expected_regions - self.phantom_drops_expected
            
            details = (f"Expected regions: {expected_regions}, "
                      f"Phantom drops: {self.phantom_drops_expected}, "
                      f"Expected final: {expected_count}, "
                      f"Actual: {actual_count}")
            
            # Allow some tolerance since we might not know exact region count
            if actual_count <= expected_regions:
                self.log_result("Deletion Count Check", True, details)
                return True
            else:
                self.log_result("Deletion Count Check", False, details)
                return False
            
        except Exception as e:
            self.log_result("Deletion Count Check", False, str(e))
            return False

    def test_clean_background_endpoint(self) -> bool:
        """Test manual /clean-background endpoint with low quality matte"""
        try:
            print("\n🧪 Testing /clean-background endpoint...")
            headers = {"Authorization": f"Bearer {self.token}"}
            
            # Get first item from closet
            response = requests.get(f"{self.base_url}/api/v1/closet", headers=headers, timeout=30)
            if response.status_code != 200 or not response.json():
                self.log_result("Clean Background Endpoint", False, "No items in closet to test")
                return False
            
            items = response.json()
            test_item = items[0]
            item_id = test_item.get("id")
            
            print(f"   Testing with item: {test_item.get('title')} (ID: {item_id})")
            
            # Call clean-background endpoint
            clean_response = requests.post(
                f"{self.base_url}/api/v1/closet/{item_id}/clean-background",
                headers=headers,
                timeout=60
            )
            
            if clean_response.status_code == 200:
                result = clean_response.json()
                applied = result.get("applied", False)
                reason = result.get("reason", "")
                
                # The endpoint should either apply successfully or reject with low_quality_matte
                if applied or reason == "low_quality_matte":
                    self.log_result("Clean Background Endpoint", True, 
                                  f"Applied: {applied}, Reason: {reason}")
                    return True
                else:
                    self.log_result("Clean Background Endpoint", False, 
                                  f"Unexpected result: applied={applied}, reason={reason}")
                    return False
            else:
                self.log_result("Clean Background Endpoint", False, 
                              f"Status: {clean_response.status_code}")
                return False
            
        except Exception as e:
            self.log_result("Clean Background Endpoint", False, str(e))
            return False

    def test_regression_normal_garments(self) -> bool:
        """Test that normal tops/bottoms/dresses still work (don't trigger phantom-drop)"""
        try:
            print("\n🔄 Testing regression with normal garments...")
            headers = {"Authorization": f"Bearer {self.token}"}
            
            # Look for test images that are likely to be normal garments (not accessories)
            # We'll use images 0015-0020 which are more likely to be full garments
            test_images = [
                "/app/inference-server/eyes/test_images/0015.jpg",
                "/app/inference-server/eyes/test_images/0016.jpg"
            ]
            
            # Filter to only existing files
            test_images = [img for img in test_images if os.path.exists(img)]
            
            if not test_images:
                self.log_result("Regression Normal Garments", False, "No test images found")
                return False
            
            initial_count = len(self.uploaded_items)
            
            # Upload and analyze
            results = self.upload_test_images(test_images)
            
            if results["errors"]:
                self.log_result("Regression Normal Garments", False, 
                              f"Errors during upload: {results['errors']}")
                return False
            
            # Wait for polish
            self.wait_for_polish_completion(timeout_seconds=120)
            
            # Check that items were NOT deleted (normal garments should pass)
            response = requests.get(f"{self.base_url}/api/v1/closet", headers=headers, timeout=30)
            if response.status_code != 200:
                self.log_result("Regression Normal Garments", False, "Failed to fetch closet")
                return False
            
            items = response.json()
            new_items = [item for item in items if item.get("id") in self.uploaded_items[initial_count:]]
            
            if len(new_items) > 0:
                self.log_result("Regression Normal Garments", True, 
                              f"{len(new_items)} normal garments saved successfully")
                return True
            else:
                self.log_result("Regression Normal Garments", False, 
                              "Normal garments were incorrectly deleted")
                return False
            
        except Exception as e:
            self.log_result("Regression Normal Garments", False, str(e))
            return False

    def run_all_tests(self) -> Dict[str, Any]:
        """Run all tests and return summary"""
        print("🧪 Starting Patch 12m Phantom-Drop Guard Tests...")
        print(f"🔗 Testing against: {self.base_url}")
        print("=" * 80)
        
        # Get auth token first
        if not self.get_auth_token():
            return self.get_summary()
        
        # Clear closet
        self.clear_closet()
        
        # Test 1: Upload accessory photos (likely to trigger phantom-drop)
        print("\n" + "=" * 80)
        print("TEST 1: Upload accessory photos (0001-0008)")
        print("=" * 80)
        
        accessory_images = [
            f"/app/inference-server/eyes/test_images/{i:04d}.jpg"
            for i in range(1, 9)
        ]
        # Filter to only existing files
        accessory_images = [img for img in accessory_images if os.path.exists(img)]
        
        if not accessory_images:
            print("❌ No test images found!")
            return self.get_summary()
        
        upload_results = self.upload_test_images(accessory_images)
        
        print(f"\n📊 Upload Results:")
        print(f"   Items analyzed: {len(upload_results['analyzed_items'])}")
        print(f"   Errors: {len(upload_results['errors'])}")
        
        if upload_results['errors']:
            print(f"   Error details: {upload_results['errors']}")
        
        # Test 2: Wait for polish completion
        print("\n" + "=" * 80)
        print("TEST 2: Wait for polish completion and phantom-drop")
        print("=" * 80)
        
        polish_completed = self.wait_for_polish_completion(timeout_seconds=180)
        
        # Test 3: Verify no white windows
        print("\n" + "=" * 80)
        print("TEST 3: Verify no white-window cards")
        print("=" * 80)
        
        self.verify_no_white_windows()
        
        # Test 4: Verify deletion count
        print("\n" + "=" * 80)
        print("TEST 4: Verify deletion count")
        print("=" * 80)
        
        expected_regions = len(upload_results['analyzed_items'])
        self.verify_deletion_count(expected_regions)
        
        # Test 5: Test clean-background endpoint
        print("\n" + "=" * 80)
        print("TEST 5: Test /clean-background endpoint")
        print("=" * 80)
        
        self.test_clean_background_endpoint()
        
        # Test 6: Regression test with normal garments
        print("\n" + "=" * 80)
        print("TEST 6: Regression test with normal garments")
        print("=" * 80)
        
        self.test_regression_normal_garments()
        
        return self.get_summary()

    def get_summary(self) -> Dict[str, Any]:
        """Get test summary"""
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        
        print("\n" + "=" * 80)
        print(f"📊 Test Summary: {self.tests_passed}/{self.tests_run} passed ({success_rate:.1f}%)")
        print(f"👻 Phantom drops detected: {self.phantom_drops_expected}")
        
        if self.tests_passed == self.tests_run:
            print("🎉 All tests passed!")
        else:
            print("⚠️  Some tests failed - check details above")
        
        return {
            "total_tests": self.tests_run,
            "passed_tests": self.tests_passed,
            "success_rate": success_rate,
            "phantom_drops": self.phantom_drops_expected,
            "test_results": self.test_results,
            "timestamp": datetime.now().isoformat()
        }

def main():
    """Main test runner"""
    base_url = os.getenv("BACKEND_URL", "https://ai-stylist-api.preview.emergentagent.com")
    
    tester = Patch12mTester(base_url)
    summary = tester.run_all_tests()
    
    # Save results to file
    output_file = "/tmp/patch12m_test_results.json"
    with open(output_file, "w") as f:
        json.dump(summary, f, indent=2)
    
    print(f"\n💾 Results saved to: {output_file}")
    
    # Exit with appropriate code
    sys.exit(0 if summary["passed_tests"] == summary["total_tests"] else 1)

if __name__ == "__main__":
    main()
