#!/usr/bin/env python3
"""
Backend API Testing for DressApp Chrome Extension Size Chart Analyzer
Tests the /api/v1/sizes/analyze-chart endpoint and related functionality.
"""

import requests
import json
import base64
import sys
import os
from datetime import datetime
from typing import Dict, Any, List

class SizeChartAnalyzerTester:
    def __init__(self, base_url: str = "https://ai-stylist-api.preview.emergentagent.com"):
        self.base_url = base_url
        self.token = None
        self.user_id = None
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
                self.user_id = data.get("user", {}).get("id")
                self.log_result("Auth Token Acquisition", True, f"Token obtained for user: {self.user_id}")
                return True
            else:
                self.log_result("Auth Token Acquisition", False, f"Status: {response.status_code}, Body: {response.text[:200]}")
                return False
        except Exception as e:
            self.log_result("Auth Token Acquisition", False, str(e))
            return False

    def test_analyze_chart_401_without_auth(self) -> bool:
        """Test that analyze-chart returns 401 without Authorization header"""
        try:
            data = {
                "chart_html": "<table><tr><td>S</td><td>M</td><td>L</td></tr></table>"
            }
            
            response = requests.post(
                f"{self.base_url}/api/v1/sizes/analyze-chart",
                json=data,
                timeout=10
            )
            
            if response.status_code == 401:
                error_detail = response.json().get("detail", "")
                self.log_result("Analyze Chart 401 Without Auth", True, f"Correct 401 response: {error_detail}")
                return True
            else:
                self.log_result("Analyze Chart 401 Without Auth", False, 
                              f"Expected 401, got {response.status_code}")
                return False
                
        except Exception as e:
            self.log_result("Analyze Chart 401 Without Auth", False, str(e))
            return False

    def test_analyze_chart_with_chart_html(self) -> bool:
        """Test analyze-chart with chart_html only"""
        try:
            headers = {"Authorization": f"Bearer {self.token}"}
            
            # Sample size chart HTML
            chart_html = """
            <table>
                <tr><th>Size</th><th>Chest (cm)</th><th>Waist (cm)</th></tr>
                <tr><td>S</td><td>86-91</td><td>71-76</td></tr>
                <tr><td>M</td><td>91-97</td><td>76-81</td></tr>
                <tr><td>L</td><td>97-102</td><td>81-86</td></tr>
                <tr><td>XL</td><td>102-107</td><td>86-91</td></tr>
            </table>
            """
            
            data = {
                "chart_html": chart_html,
                "garment_type": "shirt",
                "store": "TestStore"
            }
            
            response = requests.post(
                f"{self.base_url}/api/v1/sizes/analyze-chart",
                json=data,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                
                # Validate AnalyzeChartOut schema
                required_fields = [
                    "recommended_size", "confidence", "garment_type", 
                    "size_chart_units", "matched_columns", "reasoning", 
                    "alternatives", "source", "elapsed_ms", "has_measurements"
                ]
                
                missing_fields = [f for f in required_fields if f not in result]
                if missing_fields:
                    self.log_result("Analyze Chart with HTML", False, 
                                  f"Missing fields: {missing_fields}")
                    return False
                
                # Validate types
                if not isinstance(result["confidence"], (int, float)):
                    self.log_result("Analyze Chart with HTML", False, 
                                  f"confidence is not a number: {type(result['confidence'])}")
                    return False
                
                if not isinstance(result["matched_columns"], list):
                    self.log_result("Analyze Chart with HTML", False, 
                                  f"matched_columns is not a list: {type(result['matched_columns'])}")
                    return False
                
                if not isinstance(result["alternatives"], list):
                    self.log_result("Analyze Chart with HTML", False, 
                                  f"alternatives is not a list: {type(result['alternatives'])}")
                    return False
                
                if not isinstance(result["elapsed_ms"], int):
                    self.log_result("Analyze Chart with HTML", False, 
                                  f"elapsed_ms is not an int: {type(result['elapsed_ms'])}")
                    return False
                
                if not isinstance(result["has_measurements"], bool):
                    self.log_result("Analyze Chart with HTML", False, 
                                  f"has_measurements is not a bool: {type(result['has_measurements'])}")
                    return False
                
                # Source should be one of: gemma, qwen, heuristic, none
                valid_sources = ["gemma", "qwen", "heuristic", "none"]
                if result["source"] not in valid_sources:
                    self.log_result("Analyze Chart with HTML", False, 
                                  f"Invalid source: {result['source']}, expected one of {valid_sources}")
                    return False
                
                self.log_result("Analyze Chart with HTML", True, 
                              f"Size: {result.get('recommended_size')}, Confidence: {result['confidence']}, "
                              f"Source: {result['source']}, Has measurements: {result['has_measurements']}, "
                              f"Elapsed: {result['elapsed_ms']}ms")
                return True
            else:
                self.log_result("Analyze Chart with HTML", False, 
                              f"Status: {response.status_code}, Body: {response.text[:300]}")
                return False
                
        except Exception as e:
            self.log_result("Analyze Chart with HTML", False, str(e))
            return False

    def test_analyze_chart_with_screenshot(self) -> bool:
        """Test analyze-chart with chart_screenshot_b64 only"""
        try:
            headers = {"Authorization": f"Bearer {self.token}"}
            
            # Create a tiny 1x1 JPEG image and encode to base64
            tiny_jpeg = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\xff\xc0\x00\x11\x08\x00\x01\x00\x01\x01\x01\x11\x00\x02\x11\x01\x03\x11\x01\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x08\xff\xc4\x00\x14\x10\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00\x3f\x00\xaa\xff\xd9'
            screenshot_b64 = base64.b64encode(tiny_jpeg).decode('ascii')
            
            data = {
                "chart_screenshot_b64": screenshot_b64,
                "garment_type": "dress"
            }
            
            response = requests.post(
                f"{self.base_url}/api/v1/sizes/analyze-chart",
                json=data,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                
                # In dev env where Gemma/Qwen are unreachable, source should be 'none' or 'heuristic'
                # The endpoint should never 5xx
                valid_sources = ["gemma", "qwen", "heuristic", "none"]
                if result["source"] not in valid_sources:
                    self.log_result("Analyze Chart with Screenshot", False, 
                                  f"Invalid source: {result['source']}")
                    return False
                
                self.log_result("Analyze Chart with Screenshot", True, 
                              f"Size: {result.get('recommended_size')}, Source: {result['source']}, "
                              f"Confidence: {result['confidence']}")
                return True
            else:
                self.log_result("Analyze Chart with Screenshot", False, 
                              f"Status: {response.status_code}, Body: {response.text[:300]}")
                return False
                
        except Exception as e:
            self.log_result("Analyze Chart with Screenshot", False, str(e))
            return False

    def test_analyze_chart_empty_body_422(self) -> bool:
        """Test analyze-chart with empty body returns 422"""
        try:
            headers = {"Authorization": f"Bearer {self.token}"}
            data = {}  # Empty body - no chart_html, chart_text, or chart_screenshot_b64
            
            response = requests.post(
                f"{self.base_url}/api/v1/sizes/analyze-chart",
                json=data,
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 422:
                error_detail = response.json().get("detail", "")
                # Check if error mentions required inputs
                expected_keywords = ["chart_html", "chart_text", "chart_screenshot_b64"]
                has_expected_message = any(kw in str(error_detail).lower() for kw in expected_keywords)
                
                if has_expected_message:
                    self.log_result("Analyze Chart Empty Body 422", True, 
                                  f"Correct 422 error: {error_detail}")
                    return True
                else:
                    self.log_result("Analyze Chart Empty Body 422", False, 
                                  f"422 returned but error message doesn't mention required inputs: {error_detail}")
                    return False
            else:
                self.log_result("Analyze Chart Empty Body 422", False, 
                              f"Expected 422, got {response.status_code}, Body: {response.text[:200]}")
                return False
                
        except Exception as e:
            self.log_result("Analyze Chart Empty Body 422", False, str(e))
            return False

    def test_analyze_chart_without_measurements(self) -> bool:
        """Test analyze-chart when user has no body_measurements (should return 200 with has_measurements=false)"""
        try:
            headers = {"Authorization": f"Bearer {self.token}"}
            
            # First, ensure user has no measurements by clearing them
            patch_response = requests.patch(
                f"{self.base_url}/api/v1/users/me",
                json={"body_measurements": {}},
                headers=headers,
                timeout=10
            )
            
            if patch_response.status_code != 200:
                self.log_result("Analyze Chart Without Measurements", False, 
                              f"Failed to clear measurements: {patch_response.status_code}")
                return False
            
            # Now test analyze-chart
            chart_html = """
            <table>
                <tr><th>Size</th><th>Chest (cm)</th></tr>
                <tr><td>S</td><td>86-91</td></tr>
                <tr><td>M</td><td>91-97</td></tr>
            </table>
            """
            
            data = {"chart_html": chart_html}
            
            response = requests.post(
                f"{self.base_url}/api/v1/sizes/analyze-chart",
                json=data,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                
                if result.get("has_measurements") == False:
                    self.log_result("Analyze Chart Without Measurements", True, 
                                  f"Correctly returned 200 with has_measurements=false, "
                                  f"Size: {result.get('recommended_size')}, Source: {result['source']}")
                    return True
                else:
                    self.log_result("Analyze Chart Without Measurements", False, 
                                  f"has_measurements should be false but got: {result.get('has_measurements')}")
                    return False
            else:
                self.log_result("Analyze Chart Without Measurements", False, 
                              f"Expected 200, got {response.status_code}, Body: {response.text[:300]}")
                return False
                
        except Exception as e:
            self.log_result("Analyze Chart Without Measurements", False, str(e))
            return False

    def test_analyze_chart_with_measurements_heuristic(self) -> bool:
        """Test analyze-chart with measurements and heuristic fallback"""
        try:
            headers = {"Authorization": f"Bearer {self.token}"}
            
            # Set user measurements
            measurements = {
                "chest": 95,
                "waist": 80,
                "hips": 100
            }
            
            patch_response = requests.patch(
                f"{self.base_url}/api/v1/users/me",
                json={"body_measurements": measurements},
                headers=headers,
                timeout=10
            )
            
            if patch_response.status_code != 200:
                self.log_result("Analyze Chart With Measurements Heuristic", False, 
                              f"Failed to set measurements: {patch_response.status_code}")
                return False
            
            # Chart with ranges that bracket the measurements
            chart_html = """
            <table>
                <tr><th>Size</th><th>Chest (cm)</th><th>Waist (cm)</th><th>Hips (cm)</th></tr>
                <tr><td>S</td><td>86-91</td><td>71-76</td><td>91-96</td></tr>
                <tr><td>M</td><td>91-97</td><td>76-81</td><td>96-101</td></tr>
                <tr><td>L</td><td>97-102</td><td>81-86</td><td>101-106</td></tr>
            </table>
            """
            
            data = {
                "chart_html": chart_html,
                "garment_type": "shirt"
            }
            
            response = requests.post(
                f"{self.base_url}/api/v1/sizes/analyze-chart",
                json=data,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                
                # Should have has_measurements=true
                if not result.get("has_measurements"):
                    self.log_result("Analyze Chart With Measurements Heuristic", False, 
                                  "has_measurements should be true")
                    return False
                
                # Should produce a recommended_size (either from LLM or heuristic)
                # In dev env, likely source='heuristic' or 'none'
                recommended_size = result.get("recommended_size")
                source = result.get("source")
                
                self.log_result("Analyze Chart With Measurements Heuristic", True, 
                              f"Size: {recommended_size}, Source: {source}, "
                              f"Confidence: {result['confidence']}, "
                              f"Matched columns: {result.get('matched_columns')}")
                return True
            else:
                self.log_result("Analyze Chart With Measurements Heuristic", False, 
                              f"Status: {response.status_code}, Body: {response.text[:300]}")
                return False
                
        except Exception as e:
            self.log_result("Analyze Chart With Measurements Heuristic", False, str(e))
            return False

    def test_users_me_endpoint(self) -> bool:
        """Test GET /api/v1/users/me returns body_measurements"""
        try:
            headers = {"Authorization": f"Bearer {self.token}"}
            
            # First set some measurements
            measurements = {
                "chest": 100,
                "waist": 85,
                "hips": 105,
                "height": 180
            }
            
            patch_response = requests.patch(
                f"{self.base_url}/api/v1/users/me",
                json={"body_measurements": measurements},
                headers=headers,
                timeout=10
            )
            
            if patch_response.status_code != 200:
                self.log_result("Users Me Endpoint", False, 
                              f"Failed to set measurements: {patch_response.status_code}")
                return False
            
            # Now get the user profile
            response = requests.get(
                f"{self.base_url}/api/v1/users/me",
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                user_data = response.json()
                
                # Check body_measurements is present
                if "body_measurements" not in user_data:
                    self.log_result("Users Me Endpoint", False, 
                                  "body_measurements field not in response")
                    return False
                
                returned_measurements = user_data.get("body_measurements", {})
                
                # Verify measurements match what we set
                if returned_measurements.get("chest") == 100 and \
                   returned_measurements.get("waist") == 85:
                    self.log_result("Users Me Endpoint", True, 
                                  f"User ID: {user_data.get('id')}, "
                                  f"Measurements: {returned_measurements}")
                    return True
                else:
                    self.log_result("Users Me Endpoint", False, 
                                  f"Measurements don't match. Expected chest=100, waist=85, "
                                  f"got: {returned_measurements}")
                    return False
            else:
                self.log_result("Users Me Endpoint", False, 
                              f"Status: {response.status_code}, Body: {response.text[:200]}")
                return False
                
        except Exception as e:
            self.log_result("Users Me Endpoint", False, str(e))
            return False

    def test_backend_startup_clean(self) -> bool:
        """Verify backend started without ImportError or TypeError"""
        try:
            # Check backend error logs
            import subprocess
            result = subprocess.run(
                ["tail", "-n", "100", "/var/log/supervisor/backend.err.log"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            log_content = result.stdout.lower()
            
            # Check for startup errors
            has_import_error = "importerror" in log_content
            has_type_error = "typeerror" in log_content
            has_startup_complete = "application startup complete" in log_content
            
            if has_import_error:
                self.log_result("Backend Startup Clean", False, 
                              "Found ImportError in backend logs")
                return False
            
            if has_type_error:
                self.log_result("Backend Startup Clean", False, 
                              "Found TypeError in backend logs")
                return False
            
            if has_startup_complete:
                self.log_result("Backend Startup Clean", True, 
                              "Backend started cleanly with no ImportError or TypeError")
                return True
            else:
                self.log_result("Backend Startup Clean", False, 
                              "Could not confirm 'Application startup complete' in logs")
                return False
                
        except Exception as e:
            self.log_result("Backend Startup Clean", False, str(e))
            return False

    def run_all_tests(self) -> Dict[str, Any]:
        """Run all tests and return summary"""
        print("🧪 Starting DressApp Size Chart Analyzer Backend Tests...")
        print(f"🔗 Testing against: {self.base_url}")
        print("=" * 70)
        
        # First check backend startup
        self.test_backend_startup_clean()
        
        # Get auth token
        if not self.get_auth_token():
            return self.get_summary()
        
        # Run all endpoint tests
        test_methods = [
            self.test_analyze_chart_401_without_auth,
            self.test_analyze_chart_with_chart_html,
            self.test_analyze_chart_with_screenshot,
            self.test_analyze_chart_empty_body_422,
            self.test_analyze_chart_without_measurements,
            self.test_analyze_chart_with_measurements_heuristic,
            self.test_users_me_endpoint
        ]
        
        for test_method in test_methods:
            try:
                test_method()
            except Exception as e:
                print(f"❌ {test_method.__name__}: EXCEPTION - {str(e)}")
                self.tests_run += 1
        
        return self.get_summary()

    def get_summary(self) -> Dict[str, Any]:
        """Get test summary"""
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        
        print("\n" + "=" * 70)
        print(f"📊 Test Summary: {self.tests_passed}/{self.tests_run} passed ({success_rate:.1f}%)")
        
        if self.tests_passed == self.tests_run:
            print("🎉 All tests passed!")
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
    base_url = os.getenv("BACKEND_URL", "https://ai-stylist-api.preview.emergentagent.com")
    
    tester = SizeChartAnalyzerTester(base_url)
    summary = tester.run_all_tests()
    
    # Save results to file
    output_file = "/tmp/size_chart_analyzer_test_results.json"
    with open(output_file, "w") as f:
        json.dump(summary, f, indent=2)
    
    print(f"\n📄 Test results saved to: {output_file}")
    
    # Exit with appropriate code
    sys.exit(0 if summary["passed_tests"] == summary["total_tests"] else 1)

if __name__ == "__main__":
    main()
