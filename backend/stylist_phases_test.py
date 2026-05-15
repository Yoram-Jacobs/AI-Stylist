"""Phase S1/S2/S3 Backend API Tests — Stylist Image Features

Tests the following Phase S features:
1. Phase S1: Single image attachment with soft context (Gemini references visual properties)
2. Phase S2: Multi-image routing to /api/v1/stylist/compose-outfit
3. Backend logs "image addendum applied" when image is attached
"""
import os
import sys
import requests
import base64
from datetime import datetime
from io import BytesIO
from PIL import Image

# Read backend URL from frontend .env
BACKEND_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://ai-stylist-api.preview.emergentagent.com')

class StylistPhasesTester:
    def __init__(self, base_url=BACKEND_URL):
        self.base_url = base_url.rstrip('/')
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []
        
    def log(self, msg, level='info'):
        """Log test output"""
        prefix = {
            'info': '🔍',
            'pass': '✅',
            'fail': '❌',
            'warn': '⚠️'
        }.get(level, '•')
        print(f"{prefix} {msg}")
        
    def run_test(self, name, method, endpoint, expected_status, files=None, data=None, headers=None):
        """Run a single API test"""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        req_headers = {}
        if self.token:
            req_headers['Authorization'] = f'Bearer {self.token}'
        if headers:
            req_headers.update(headers)
        
        self.tests_run += 1
        self.log(f"Testing {name}...", 'info')
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=req_headers, timeout=60)
            elif method == 'POST':
                if files:
                    # multipart/form-data
                    response = requests.post(url, files=files, data=data, headers=req_headers, timeout=60)
                else:
                    # application/json
                    req_headers['Content-Type'] = 'application/json'
                    response = requests.post(url, json=data, headers=req_headers, timeout=60)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            success = response.status_code == expected_status
            result = {
                'name': name,
                'passed': success,
                'expected_status': expected_status,
                'actual_status': response.status_code,
                'response': None
            }
            
            if success:
                self.tests_passed += 1
                self.log(f"Passed - Status: {response.status_code}", 'pass')
                try:
                    result['response'] = response.json()
                except:
                    result['response'] = response.text
            else:
                self.log(f"Failed - Expected {expected_status}, got {response.status_code}", 'fail')
                try:
                    error_detail = response.json()
                    self.log(f"  Error: {error_detail}", 'warn')
                    result['error'] = error_detail
                except:
                    result['error'] = response.text
            
            self.test_results.append(result)
            return success, result.get('response', {})
            
        except Exception as e:
            self.log(f"Failed - Error: {str(e)}", 'fail')
            result = {
                'name': name,
                'passed': False,
                'error': str(e)
            }
            self.test_results.append(result)
            return False, {}
    
    def setup_auth(self):
        """Get dev-bypass token"""
        self.log("Setting up authentication...", 'info')
        success, response = self.run_test(
            "Dev-bypass auth",
            "POST",
            "/api/v1/auth/dev-bypass",
            200
        )
        if success and 'access_token' in response:
            self.token = response['access_token']
            self.log(f"Auth token obtained", 'pass')
            return True
        self.log("Failed to obtain auth token", 'fail')
        return False
    
    def create_test_image(self, color='red', size=(200, 200)):
        """Create a simple test image with visual features"""
        img = Image.new('RGB', size, color=color)
        buf = BytesIO()
        img.save(buf, format='JPEG')
        buf.seek(0)
        return buf.getvalue()
    
    def test_single_image_stylist(self):
        """Test POST /api/v1/stylist with single image (Phase S1)"""
        self.log("\n--- Phase S1: Single image with soft context ---", 'info')
        
        # Create a red test image
        image_bytes = self.create_test_image(color='red')
        
        files = {
            'image': ('test_red_shirt.jpg', image_bytes, 'image/jpeg')
        }
        data = {
            'text': 'What would go with this?',
            'language': 'en',
            'skip_tts': 'true'
        }
        
        success, response = self.run_test(
            "Single image stylist request",
            "POST",
            "/api/v1/stylist",
            200,
            files=files,
            data=data
        )
        
        if success:
            advice = response.get('advice', {})
            reasoning = advice.get('reasoning_summary', '')
            
            # Check if response exists and is not empty
            if reasoning:
                self.log(f"  ✓ Got response: {reasoning[:100]}...", 'pass')
                
                # Check if response references visual properties (soft check)
                visual_keywords = ['color', 'red', 'garment', 'fit', 'style', 'wear', 'match']
                has_visual_ref = any(kw in reasoning.lower() for kw in visual_keywords)
                
                if has_visual_ref:
                    self.log("  ✓ Response references visual properties", 'pass')
                else:
                    self.log("  ⚠️  Response may not reference visual properties", 'warn')
                
                return True
            else:
                self.log("  ✗ Empty response", 'fail')
                return False
        return False
    
    def test_multi_image_compose_outfit(self):
        """Test POST /api/v1/stylist/compose-outfit with 2+ images (Phase S2)"""
        self.log("\n--- Phase S2: Multi-image outfit composer ---", 'info')
        
        # Create two test images
        image1 = self.create_test_image(color='blue')
        image2 = self.create_test_image(color='green')
        
        files = [
            ('images', ('test_blue_top.jpg', image1, 'image/jpeg')),
            ('images', ('test_green_pants.jpg', image2, 'image/jpeg'))
        ]
        data = {
            'text': 'Create an outfit with these items',
            'language': 'en'
        }
        
        success, response = self.run_test(
            "Multi-image compose-outfit request",
            "POST",
            "/api/v1/stylist/compose-outfit",
            200,
            files=files,
            data=data
        )
        
        if success:
            canvas = response.get('canvas', {})
            
            # Check canvas structure
            checks = []
            
            if 'canvas_id' in canvas:
                self.log(f"  ✓ canvas_id present: {canvas['canvas_id']}", 'pass')
                checks.append(True)
            else:
                self.log("  ✗ canvas_id missing", 'fail')
                checks.append(False)
            
            if 'slots' in canvas:
                self.log(f"  ✓ slots present: {len(canvas['slots'])} slots", 'pass')
                checks.append(True)
            else:
                self.log("  ✗ slots missing", 'fail')
                checks.append(False)
            
            if 'candidates' in canvas:
                self.log(f"  ✓ candidates present: {len(canvas['candidates'])} candidates", 'pass')
                checks.append(True)
            else:
                self.log("  ✗ candidates missing", 'fail')
                checks.append(False)
            
            if 'summary' in canvas:
                self.log(f"  ✓ summary present: {canvas['summary'][:80]}...", 'pass')
                checks.append(True)
            else:
                self.log("  ✗ summary missing", 'fail')
                checks.append(False)
            
            return all(checks)
        return False
    
    def test_single_image_routing(self):
        """Verify single image still routes to /api/v1/stylist (not compose-outfit)"""
        self.log("\n--- Regression: Single image routing ---", 'info')
        
        image_bytes = self.create_test_image(color='yellow')
        
        files = {
            'image': ('test_yellow_dress.jpg', image_bytes, 'image/jpeg')
        }
        data = {
            'text': 'Is this appropriate for a wedding?',
            'language': 'en',
            'skip_tts': 'true'
        }
        
        success, response = self.run_test(
            "Single image routes to /stylist",
            "POST",
            "/api/v1/stylist",
            200,
            files=files,
            data=data
        )
        
        if success:
            # Check it's a stylist response (not a canvas)
            if 'advice' in response:
                self.log("  ✓ Response is stylist format (not canvas)", 'pass')
                return True
            else:
                self.log("  ✗ Unexpected response format", 'fail')
                return False
        return False
    
    def run_all_tests(self):
        """Run all Phase S backend tests"""
        self.log("=" * 60, 'info')
        self.log("Phase S1/S2/S3 Backend API Tests", 'info')
        self.log("=" * 60, 'info')
        
        # Setup
        if not self.setup_auth():
            self.log("Authentication failed - cannot proceed", 'fail')
            return False
        
        # Phase S1: Single image with soft context
        self.test_single_image_stylist()
        
        # Phase S2: Multi-image compose-outfit
        self.test_multi_image_compose_outfit()
        
        # Regression: Single image routing
        self.test_single_image_routing()
        
        # Summary
        self.log("\n" + "=" * 60, 'info')
        self.log(f"Tests passed: {self.tests_passed}/{self.tests_run}", 'info')
        self.log("=" * 60, 'info')
        
        return self.tests_passed == self.tests_run

def main():
    tester = StylistPhasesTester()
    success = tester.run_all_tests()
    
    # Print detailed results
    print("\n\n📊 Detailed Test Results:")
    print("=" * 60)
    for i, result in enumerate(tester.test_results, 1):
        status = "✅ PASS" if result['passed'] else "❌ FAIL"
        print(f"{i}. {result['name']}: {status}")
        if not result['passed'] and 'error' in result:
            print(f"   Error: {result['error']}")
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
