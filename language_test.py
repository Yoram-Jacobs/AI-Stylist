#!/usr/bin/env python3
"""
DressApp Language Selector Testing
Tests the specific language functionality requested in the review.
"""

import requests
import sys
import json
import time
from typing import Dict, Any

class LanguageTester:
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
                    token: str = None, files: Dict = None, timeout: int = 30) -> tuple[bool, Dict, int]:
        """Make HTTP request with error handling"""
        url = f"{self.base_url}/api/v1{endpoint}"
        headers = {}
        
        if token:
            headers['Authorization'] = f'Bearer {token}'
        
        if files:
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
            print(f"✅ Authentication successful")
            return True
        else:
            print(f"❌ Authentication failed: {status}")
            return False

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
            
            # Print sample content for verification
            if reasoning_summary:
                print(f"   Sample reasoning: {reasoning_summary[:100]}...")
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
            
            # Print sample content for verification
            if reasoning_summary:
                print(f"   Sample reasoning: {reasoning_summary[:100]}...")
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
            
            # Check if enum fields are in expected English values
            enum_fields_english = True
            if category and category.lower() not in ['top', 'bottom', 'outerwear', 'full body', 'footwear', 'accessories', 'underwear']:
                enum_fields_english = False
            
            has_content = bool(title)
            
            self.log_test("Garment Vision Hebrew Localization", hebrew_chars and enum_fields_english and has_content,
                         f"Hebrew chars: {hebrew_chars}, Enums English: {enum_fields_english}, Has content: {has_content}")
            
            # Print sample content for verification
            if title:
                print(f"   Sample title: {title}")
            if caption:
                print(f"   Sample caption: {caption[:100]}...")
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
            ('POST', '/auth/dev-bypass')  # Fixed: dev-bypass is POST, not GET
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

    def run_tests(self):
        """Run all language selector tests"""
        print("🚀 Starting DressApp Language Selector Tests...")
        print(f"🌐 Testing against: {self.base_url}")
        print("=" * 60)
        
        # Setup authentication
        if not self.setup_auth():
            return self.print_summary()
        
        # Run language tests
        self.test_language_persistence()
        self.test_language_validation()
        self.test_stylist_language_localization()
        self.test_garment_vision_language_localization()
        self.test_existing_endpoints_regression()
        
        return self.print_summary()

    def print_summary(self):
        """Print test summary"""
        print("\n" + "=" * 60)
        print("📊 LANGUAGE SELECTOR TEST RESULTS")
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
    tester = LanguageTester()
    results = tester.run_tests()
    
    # Return appropriate exit code
    return 0 if results["success_rate"] >= 80 else 1

if __name__ == "__main__":
    sys.exit(main())