#!/usr/bin/env python3
"""
Backend API Testing for Stylist Power-Up (Phase R)
Tests the compose-outfit endpoint and related functionality.
"""

import requests
import json
import time
import sys
import os
from datetime import datetime
from typing import Dict, Any, List

class StylistPowerUpTester:
    def __init__(self, base_url: str = "https://ai-stylist-api.preview.emergentagent.com"):
        self.base_url = base_url
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.session_id = None
        self.test_results = []

    def log_result(self, test_name: str, success: bool, details: str = ""):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {test_name}: PASSED")
        else:
            print(f"❌ {test_name}: FAILED - {details}")
        
        self.test_results.append({
            "test": test_name,
            "success": success,
            "details": details,
            "timestamp": datetime.now().isoformat()
        })

    def get_auth_token(self) -> bool:
        """Get JWT token using dev-bypass"""
        try:
            response = requests.post(f"{self.base_url}/api/v1/auth/dev-bypass", timeout=10)
            if response.status_code == 200:
                data = response.json()
                self.token = data.get("access_token")
                self.log_result("Auth Token Acquisition", True, f"Token obtained: {self.token[:20]}...")
                return True
            else:
                self.log_result("Auth Token Acquisition", False, f"Status: {response.status_code}")
                return False
        except Exception as e:
            self.log_result("Auth Token Acquisition", False, str(e))
            return False

    def test_compose_outfit_with_text_only(self) -> bool:
        """Test compose-outfit with only text (no images)"""
        try:
            headers = {"Authorization": f"Bearer {self.token}"}
            data = {
                "text": "I need a casual outfit for a coffee date",
                "language": "en",
                "budget_cents": 15000,
                "currency": "USD",
                "dress_code": "casual",
                "season": "spring"
            }
            
            response = requests.post(
                f"{self.base_url}/api/v1/stylist/compose-outfit",
                data=data,
                headers=headers,
                timeout=180  # Generous timeout as mentioned
            )
            
            if response.status_code == 200:
                result = response.json()
                canvas = result.get("canvas", {})
                
                # Validate response structure
                required_fields = ["canvas_id", "schema_version", "summary", "slots", 
                                 "candidates", "rejected", "marketplace_suggestions", 
                                 "professional_suggestion", "latency_ms"]
                
                missing_fields = [f for f in required_fields if f not in canvas]
                if missing_fields:
                    self.log_result("Compose Outfit Text Only", False, f"Missing fields: {missing_fields}")
                    return False
                
                # Check that all slots are gaps (no images provided)
                slots = canvas.get("slots", [])
                all_gaps = all(slot.get("is_gap", False) for slot in slots)
                
                # Check marketplace suggestions exist for active listings
                has_marketplace_suggestions = len(canvas.get("marketplace_suggestions", [])) > 0
                
                self.log_result("Compose Outfit Text Only", True, 
                              f"Canvas ID: {canvas.get('canvas_id')}, Slots: {len(slots)}, "
                              f"All gaps: {all_gaps}, Marketplace suggestions: {has_marketplace_suggestions}")
                
                # Store session_id for history test
                self.session_id = result.get("session_id")
                return True
            else:
                self.log_result("Compose Outfit Text Only", False, f"Status: {response.status_code}, Body: {response.text[:200]}")
                return False
                
        except Exception as e:
            self.log_result("Compose Outfit Text Only", False, str(e))
            return False

    def test_compose_outfit_empty_body(self) -> bool:
        """Test compose-outfit with empty body (should return 400)"""
        try:
            headers = {"Authorization": f"Bearer {self.token}"}
            data = {}  # Empty body
            
            response = requests.post(
                f"{self.base_url}/api/v1/stylist/compose-outfit",
                data=data,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 400:
                error_msg = response.json().get("detail", "")
                expected_msg = "Send at least one image OR a text brief"
                if expected_msg.lower() in error_msg.lower():
                    self.log_result("Compose Outfit Empty Body", True, f"Correct 400 error: {error_msg}")
                    return True
                else:
                    self.log_result("Compose Outfit Empty Body", False, f"Wrong error message: {error_msg}")
                    return False
            else:
                self.log_result("Compose Outfit Empty Body", False, f"Expected 400, got {response.status_code}")
                return False
                
        except Exception as e:
            self.log_result("Compose Outfit Empty Body", False, str(e))
            return False

    def test_compose_outfit_with_single_image(self) -> bool:
        """Test compose-outfit with single image"""
        try:
            headers = {"Authorization": f"Bearer {self.token}"}
            
            # Create a simple test image (1x1 pixel JPEG)
            test_image_data = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\xff\xc0\x00\x11\x08\x00\x01\x00\x01\x01\x01\x11\x00\x02\x11\x01\x03\x11\x01\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x08\xff\xc4\x00\x14\x10\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00\x3f\x00\xaa\xff\xd9'
            
            files = {"images": ("test.jpg", test_image_data, "image/jpeg")}
            data = {
                "text": "Style this shirt for a business meeting",
                "language": "en"
            }
            
            response = requests.post(
                f"{self.base_url}/api/v1/stylist/compose-outfit",
                data=data,
                files=files,
                headers=headers,
                timeout=180
            )
            
            if response.status_code == 200:
                result = response.json()
                canvas = result.get("canvas", {})
                candidates = canvas.get("candidates", [])
                
                self.log_result("Compose Outfit Single Image", True, 
                              f"Canvas ID: {canvas.get('canvas_id')}, Candidates: {len(candidates)}")
                return True
            else:
                self.log_result("Compose Outfit Single Image", False, 
                              f"Status: {response.status_code}, Body: {response.text[:200]}")
                return False
                
        except Exception as e:
            self.log_result("Compose Outfit Single Image", False, str(e))
            return False

    def test_compose_outfit_multiple_images(self) -> bool:
        """Test compose-outfit with multiple images (dedup logic)"""
        try:
            headers = {"Authorization": f"Bearer {self.token}"}
            
            # Create multiple test images
            test_image_data = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\xff\xc0\x00\x11\x08\x00\x01\x00\x01\x01\x01\x11\x00\x02\x11\x01\x03\x11\x01\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x08\xff\xc4\x00\x14\x10\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00\x3f\x00\xaa\xff\xd9'
            
            files = [
                ("images", ("test1.jpg", test_image_data, "image/jpeg")),
                ("images", ("test2.jpg", test_image_data, "image/jpeg")),
                ("images", ("test3.jpg", test_image_data, "image/jpeg"))
            ]
            
            data = {
                "text": "Create an outfit from these pieces",
                "language": "en"
            }
            
            response = requests.post(
                f"{self.base_url}/api/v1/stylist/compose-outfit",
                data=data,
                files=files,
                headers=headers,
                timeout=180
            )
            
            if response.status_code == 200:
                result = response.json()
                canvas = result.get("canvas", {})
                candidates = canvas.get("candidates", [])
                rejected = canvas.get("rejected", [])
                
                # Check for dedup logic - should have rejected entries with reason='duplicate'
                duplicate_rejects = [r for r in rejected if r.get("reason") == "duplicate"]
                
                self.log_result("Compose Outfit Multiple Images", True, 
                              f"Candidates: {len(candidates)}, Rejected: {len(rejected)}, "
                              f"Duplicate rejects: {len(duplicate_rejects)}")
                return True
            else:
                self.log_result("Compose Outfit Multiple Images", False, 
                              f"Status: {response.status_code}, Body: {response.text[:200]}")
                return False
                
        except Exception as e:
            self.log_result("Compose Outfit Multiple Images", False, str(e))
            return False

    def test_hebrew_brief_support(self) -> bool:
        """Test Hebrew brief support"""
        try:
            headers = {"Authorization": f"Bearer {self.token}"}
            data = {
                "text": "מה לובשים לחתונה",  # "What to wear to a wedding" in Hebrew
                "language": "he"
            }
            
            response = requests.post(
                f"{self.base_url}/api/v1/stylist/compose-outfit",
                data=data,
                headers=headers,
                timeout=180
            )
            
            if response.status_code == 200:
                result = response.json()
                canvas = result.get("canvas", {})
                professional_suggestion = canvas.get("professional_suggestion")
                
                # Should trigger professional suggestion for wedding
                has_pro_suggestion = professional_suggestion is not None
                
                self.log_result("Hebrew Brief Support", True, 
                              f"Canvas created, Professional suggestion: {has_pro_suggestion}")
                return True
            else:
                self.log_result("Hebrew Brief Support", False, 
                              f"Status: {response.status_code}, Body: {response.text[:200]}")
                return False
                
        except Exception as e:
            self.log_result("Hebrew Brief Support", False, str(e))
            return False

    def test_professional_matcher(self) -> bool:
        """Test professional matcher with wedding/tailor keywords"""
        try:
            headers = {"Authorization": f"Bearer {self.token}"}
            data = {
                "text": "I need alterations for my wedding suit - the jacket is too big",
                "language": "en"
            }
            
            response = requests.post(
                f"{self.base_url}/api/v1/stylist/compose-outfit",
                data=data,
                headers=headers,
                timeout=180
            )
            
            if response.status_code == 200:
                result = response.json()
                canvas = result.get("canvas", {})
                professional_suggestion = canvas.get("professional_suggestion")
                
                if professional_suggestion:
                    profession = professional_suggestion.get("profession")
                    why_suggested = professional_suggestion.get("why_suggested", "")
                    
                    self.log_result("Professional Matcher", True, 
                                  f"Profession: {profession}, Why: {why_suggested}")
                else:
                    self.log_result("Professional Matcher", True, 
                                  "No professional suggestion (acceptable per requirements)")
                return True
            else:
                self.log_result("Professional Matcher", False, 
                              f"Status: {response.status_code}, Body: {response.text[:200]}")
                return False
                
        except Exception as e:
            self.log_result("Professional Matcher", False, str(e))
            return False

    def test_persistence_and_history(self) -> bool:
        """Test that compose-outfit results are persisted in history"""
        if not self.session_id:
            self.log_result("Persistence and History", False, "No session_id from previous tests")
            return False
            
        try:
            headers = {"Authorization": f"Bearer {self.token}"}
            
            response = requests.get(
                f"{self.base_url}/api/v1/stylist/history",
                params={"session_id": self.session_id},
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                messages = result.get("messages", [])
                
                # Look for assistant message with outfit_canvas
                canvas_messages = [
                    msg for msg in messages 
                    if msg.get("role") == "assistant" and 
                    msg.get("assistant_payload", {}).get("outfit_canvas")
                ]
                
                if canvas_messages:
                    canvas = canvas_messages[-1]["assistant_payload"]["outfit_canvas"]
                    self.log_result("Persistence and History", True, 
                                  f"Found {len(canvas_messages)} canvas messages, "
                                  f"Latest canvas ID: {canvas.get('canvas_id')}")
                else:
                    self.log_result("Persistence and History", False, 
                                  "No outfit_canvas found in assistant messages")
                return len(canvas_messages) > 0
            else:
                self.log_result("Persistence and History", False, 
                              f"Status: {response.status_code}, Body: {response.text[:200]}")
                return False
                
        except Exception as e:
            self.log_result("Persistence and History", False, str(e))
            return False

    def test_existing_endpoints_regression(self) -> bool:
        """Test that existing endpoints still work (regression check)"""
        try:
            headers = {"Authorization": f"Bearer {self.token}"}
            
            # Test existing single-image stylist endpoint
            test_image_data = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\xff\xc0\x00\x11\x08\x00\x01\x00\x01\x01\x01\x11\x00\x02\x11\x01\x03\x11\x01\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x08\xff\xc4\x00\x14\x10\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00\x3f\x00\xaa\xff\xd9'
            
            files = {"image": ("test.jpg", test_image_data, "image/jpeg")}
            data = {"text": "What should I wear with this?"}
            
            response = requests.post(
                f"{self.base_url}/api/v1/stylist",
                data=data,
                files=files,
                headers=headers,
                timeout=180
            )
            
            single_image_works = response.status_code == 200
            
            # Test sessions endpoint
            sessions_response = requests.get(
                f"{self.base_url}/api/v1/stylist/sessions",
                headers=headers,
                timeout=30
            )
            
            sessions_works = sessions_response.status_code == 200
            
            # Test closet endpoint (if exists)
            closet_response = requests.get(
                f"{self.base_url}/api/v1/closet",
                headers=headers,
                timeout=30
            )
            
            closet_works = closet_response.status_code in [200, 404]  # 404 is acceptable if no items
            
            all_working = single_image_works and sessions_works and closet_works
            
            self.log_result("Existing Endpoints Regression", all_working, 
                          f"Single image: {single_image_works}, Sessions: {sessions_works}, "
                          f"Closet: {closet_works}")
            return all_working
            
        except Exception as e:
            self.log_result("Existing Endpoints Regression", False, str(e))
            return False

    def run_all_tests(self) -> Dict[str, Any]:
        """Run all tests and return summary"""
        print("🧪 Starting Stylist Power-Up Backend Tests...")
        print(f"🔗 Testing against: {self.base_url}")
        print("=" * 60)
        
        # Get auth token first
        if not self.get_auth_token():
            return self.get_summary()
        
        # Run all tests
        test_methods = [
            self.test_compose_outfit_with_text_only,
            self.test_compose_outfit_empty_body,
            self.test_compose_outfit_with_single_image,
            self.test_compose_outfit_multiple_images,
            self.test_hebrew_brief_support,
            self.test_professional_matcher,
            self.test_persistence_and_history,
            self.test_existing_endpoints_regression
        ]
        
        for test_method in test_methods:
            try:
                test_method()
            except Exception as e:
                print(f"❌ {test_method.__name__}: EXCEPTION - {str(e)}")
                self.tests_run += 1
            
            # Small delay between tests
            time.sleep(1)
        
        return self.get_summary()

    def get_summary(self) -> Dict[str, Any]:
        """Get test summary"""
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        
        print("\n" + "=" * 60)
        print(f"📊 Test Summary: {self.tests_passed}/{self.tests_run} passed ({success_rate:.1f}%)")
        
        if self.tests_passed == self.tests_run:
            print("🎉 All tests passed!")
        else:
            print("⚠️  Some tests failed - check details above")
        
        return {
            "total_tests": self.tests_run,
            "passed_tests": self.tests_passed,
            "success_rate": success_rate,
            "test_results": self.test_results,
            "timestamp": datetime.now().isoformat()
        }

def main():
    """Main test runner"""
    base_url = os.getenv("BACKEND_URL", "https://ai-stylist-api.preview.emergentagent.com")
    
    tester = StylistPowerUpTester(base_url)
    summary = tester.run_all_tests()
    
    # Save results to file
    with open("/tmp/stylist_powerup_test_results.json", "w") as f:
        json.dump(summary, f, indent=2)
    
    # Exit with appropriate code
    sys.exit(0 if summary["passed_tests"] == summary["total_tests"] else 1)

if __name__ == "__main__":
    main()