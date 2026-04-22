#!/usr/bin/env python3
"""
Phase M: System-Native Speech Backend Tests
Tests the skip_tts parameter functionality for POST /api/v1/stylist
"""

import requests
import sys
import json
import time
from typing import Dict, Any

class PhaseMTester:
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

    def get_auth_token(self):
        """Get dev-bypass token"""
        try:
            response = requests.post(f"{self.base_url}/api/v1/auth/dev-bypass", timeout=10)
            if response.status_code == 200:
                data = response.json()
                self.dev_token = data.get('access_token')
                print(f"✅ Got auth token: {self.dev_token[:20]}...")
                return True
            else:
                print(f"❌ Auth failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Auth error: {e}")
            return False

    def make_stylist_request(self, data: Dict, files: Dict = None, timeout: int = 120) -> tuple[bool, Dict, int]:
        """Make stylist request with error handling"""
        headers = {'Authorization': f'Bearer {self.dev_token}'}
        url = f"{self.base_url}/api/v1/stylist"
        
        try:
            if files:
                response = requests.post(url, data=data, files=files, headers=headers, timeout=timeout)
            else:
                response = requests.post(url, data=data, headers=headers, timeout=timeout)
            
            try:
                response_data = response.json() if response.content else {}
            except:
                response_data = {"raw_response": response.text}
            
            return True, response_data, response.status_code
        except Exception as e:
            return False, {"error": str(e)}, 0

    def test_skip_tts_true(self):
        """Test skip_tts=true returns no audio but has spoken_reply"""
        print("🔄 Testing skip_tts=true...")
        
        data = {
            'text': 'What should I wear today for work?',
            'skip_tts': 'true'
        }
        
        success, response_data, status = self.make_stylist_request(data)
        
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
            self.log_test("Skip TTS True", all_valid, 
                         f"No audio: {no_audio}, Spoken: {len(spoken_reply)} chars, Reasoning: {len(reasoning_summary)} chars")
        else:
            self.log_test("Skip TTS True", False, f"Status: {status}, Data: {response_data}")

    def test_skip_tts_default(self):
        """Test default behavior (skip_tts not provided) returns audio"""
        print("🔄 Testing skip_tts default...")
        
        data = {'text': 'What should I wear today for work?'}
        
        success, response_data, status = self.make_stylist_request(data)
        
        if success and status == 200:
            advice = response_data.get('advice', {})
            tts_audio_base64 = advice.get('tts_audio_base64', '')
            spoken_reply = advice.get('spoken_reply', '')
            
            # Key requirements: has audio and spoken content
            has_audio = len(tts_audio_base64.strip()) > 0
            has_spoken_reply = len(spoken_reply.strip()) > 0
            
            all_valid = has_audio and has_spoken_reply
            self.log_test("Skip TTS Default", all_valid, 
                         f"Has audio: {has_audio} ({len(tts_audio_base64)} chars), Spoken: {len(spoken_reply)} chars")
        else:
            self.log_test("Skip TTS Default", False, f"Status: {status}, Data: {response_data}")

    def test_skip_tts_false_explicit(self):
        """Test skip_tts=false explicitly set includes audio"""
        print("🔄 Testing skip_tts=false explicit...")
        
        data = {
            'text': 'What should I wear today for work?',
            'skip_tts': 'false'
        }
        
        success, response_data, status = self.make_stylist_request(data)
        
        if success and status == 200:
            advice = response_data.get('advice', {})
            tts_audio_base64 = advice.get('tts_audio_base64', '')
            spoken_reply = advice.get('spoken_reply', '')
            
            # Key requirements: has audio and spoken content (parity with default)
            has_audio = len(tts_audio_base64.strip()) > 0
            has_spoken_reply = len(spoken_reply.strip()) > 0
            
            all_valid = has_audio and has_spoken_reply
            self.log_test("Skip TTS False Explicit", all_valid, 
                         f"Has audio: {has_audio} ({len(tts_audio_base64)} chars), Spoken: {len(spoken_reply)} chars")
        else:
            self.log_test("Skip TTS False Explicit", False, f"Status: {status}, Data: {response_data}")

    def test_voice_audio_with_skip_tts(self):
        """Test voice_audio + skip_tts=true still attempts transcription"""
        print("🔄 Testing voice_audio + skip_tts=true...")
        
        # Create minimal WebM audio file
        webm_bytes = bytes([
            0x1A, 0x45, 0xDF, 0xA3,  # EBML header
            0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x1F,
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
        
        success, response_data, status = self.make_stylist_request(data, files)
        
        # This might fail due to invalid audio, but we're testing the flow
        if success and status == 200:
            advice = response_data.get('advice', {})
            tts_audio_base64 = advice.get('tts_audio_base64')
            
            # Key requirements: attempted transcription, no audio output
            has_transcript_field = 'transcript' in advice
            no_audio = tts_audio_base64 is None or tts_audio_base64 == ""
            
            all_valid = has_transcript_field and no_audio
            self.log_test("Voice Audio Skip TTS", all_valid, 
                         f"Transcript field: {has_transcript_field}, No audio: {no_audio}")
        elif status == 400:
            # Expected if audio is invalid - test that it doesn't 500
            self.log_test("Voice Audio Skip TTS", True, 
                         f"Graceful 400 error for invalid audio")
        else:
            self.log_test("Voice Audio Skip TTS", False, f"Status: {status}")

    def test_skip_tts_invalid_value(self):
        """Test invalid skip_tts value doesn't 500"""
        print("🔄 Testing invalid skip_tts value...")
        
        data = {
            'text': 'What should I wear today for work?',
            'skip_tts': 'banana'  # Invalid value
        }
        
        success, response_data, status = self.make_stylist_request(data)
        
        # Should either reject with 4xx or coerce cleanly, but NOT 500
        if success:
            not_500 = status != 500
            if status == 200:
                # If it coerced cleanly, check the response is valid
                advice = response_data.get('advice', {})
                has_reasoning = bool(advice.get('reasoning_summary'))
                coerced_cleanly = has_reasoning
                self.log_test("Skip TTS Invalid Value", not_500 and coerced_cleanly, 
                             f"Status: {status}, Coerced cleanly: {coerced_cleanly}")
            elif 400 <= status < 500:
                # Rejected with 4xx - also acceptable
                self.log_test("Skip TTS Invalid Value", True, 
                             f"Rejected with 4xx: {status}")
            else:
                self.log_test("Skip TTS Invalid Value", not_500, 
                             f"Status: {status} (not 500)")
        else:
            self.log_test("Skip TTS Invalid Value", False, f"Request failed")

    def test_hebrew_localization_skip_tts(self):
        """Test Hebrew localization with skip_tts=true"""
        print("🔄 Testing Hebrew localization + skip_tts=true...")
        
        data = {
            'text': 'What should I wear today for work?',
            'language': 'he',
            'skip_tts': 'true'
        }
        
        success, response_data, status = self.make_stylist_request(data)
        
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
            self.log_test("Hebrew Skip TTS", all_valid,
                         f"Hebrew chars: {hebrew_chars}, Content: {has_content}, No audio: {no_audio}")
        else:
            self.log_test("Hebrew Skip TTS", False, f"Status: {status}")

    def test_stylist_history_regression(self):
        """Test GET /stylist/history still works"""
        print("🔄 Testing stylist history regression...")
        
        try:
            headers = {'Authorization': f'Bearer {self.dev_token}'}
            response = requests.get(f"{self.base_url}/api/v1/stylist/history", headers=headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                has_session_id = 'session_id' in data
                has_messages = 'messages' in data and isinstance(data['messages'], list)
                
                all_valid = has_session_id and has_messages
                self.log_test("Stylist History Regression", all_valid, 
                             f"Session ID: {has_session_id}, Messages: {len(data.get('messages', []))}")
            else:
                self.log_test("Stylist History Regression", False, f"Status: {response.status_code}")
        except Exception as e:
            self.log_test("Stylist History Regression", False, f"Error: {e}")

    def test_closet_analyze_regression(self):
        """Test /closet/analyze endpoint unchanged"""
        print("🔄 Testing closet analyze regression...")
        
        # Use a small test image
        test_image_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
        
        analyze_data = {
            "image_base64": test_image_b64,
            "multi": False
        }
        
        try:
            headers = {'Authorization': f'Bearer {self.dev_token}', 'Content-Type': 'application/json'}
            response = requests.post(f"{self.base_url}/api/v1/closet/analyze", 
                                   json=analyze_data, headers=headers, timeout=90)
            
            if response.status_code == 200:
                data = response.json()
                has_title = 'title' in data
                has_category = 'category' in data
                has_colors = 'colors' in data
                
                all_valid = has_title and has_category and has_colors
                self.log_test("Closet Analyze Regression", all_valid, 
                             f"Title: {has_title}, Category: {has_category}, Colors: {has_colors}")
            else:
                self.log_test("Closet Analyze Regression", False, f"Status: {response.status_code}")
        except Exception as e:
            self.log_test("Closet Analyze Regression", False, f"Error: {e}")

    def run_all_tests(self):
        """Run all Phase M tests"""
        print("🚀 Starting Phase M: System-Native Speech Backend Tests")
        print(f"📍 Testing against: {self.base_url}")
        print("=" * 60)
        
        # Get auth token
        if not self.get_auth_token():
            print("❌ Cannot proceed without auth token")
            return self.generate_report()
        
        # Run Phase M specific tests
        print("\n🎤 Phase M: skip_tts Parameter Tests")
        self.test_skip_tts_true()
        self.test_skip_tts_default()
        self.test_skip_tts_false_explicit()
        self.test_voice_audio_with_skip_tts()
        self.test_skip_tts_invalid_value()
        self.test_hebrew_localization_skip_tts()
        
        # Regression tests
        print("\n🔄 Regression Tests")
        self.test_stylist_history_regression()
        self.test_closet_analyze_regression()
        
        return self.generate_report()

    def generate_report(self):
        """Generate final test report"""
        print("\n" + "=" * 60)
        print("📊 PHASE M TEST RESULTS")
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
    tester = PhaseMTester()
    results = tester.run_all_tests()
    
    # Return appropriate exit code
    return 0 if results["success_rate"] >= 80 else 1

if __name__ == "__main__":
    sys.exit(main())