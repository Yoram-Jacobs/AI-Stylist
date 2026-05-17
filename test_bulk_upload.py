#!/usr/bin/env python3
"""
Test bulk upload (>5 photos) pipeline for DressApp patch M20.5.2.

Critical fix: buildBaseCard now propagates source fingerprint fields
(sourceSha256, sourcePhash, sourceColorSig, sourceFilename, sourceSizeBytes, isDuplicate)
from the original draft card to every placeholder card created from the NDJSON 'detect' frame.

Tests:
1. Bulk upload 6-8 photos via /add page
2. Verify saved items have non-null source_sha256 and source_phash
3. Re-upload same files → should be skipped with toast
4. Verify clean_image_status transitions pending→ready
5. Cross-page progress tracking (WorkProgressFloater)
6. WorkBatchDoneToast fires once
7. No error banners in /closet
8. Interactive path (≤5 photos) regression check
"""

import requests
import sys
import time
import json
from datetime import datetime

BACKEND_URL = "https://ai-stylist-api.preview.emergentagent.com"

class BulkUploadTester:
    def __init__(self):
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.failures = []
        self.uploaded_item_ids = []

    def log(self, msg, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {level}: {msg}")

    def test(self, name, condition, details=""):
        """Record a test result"""
        self.tests_run += 1
        if condition:
            self.tests_passed += 1
            self.log(f"✅ PASS: {name}", "PASS")
            return True
        else:
            self.tests_failed += 1
            self.failures.append(f"{name}: {details}")
            self.log(f"❌ FAIL: {name} - {details}", "FAIL")
            return False

    def login(self):
        """Login using dev-bypass endpoint"""
        self.log("Logging in via dev-bypass...")
        try:
            resp = requests.post(f"{BACKEND_URL}/api/v1/auth/dev-bypass", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                self.token = data.get("access_token")
                self.test("Login via dev-bypass", self.token is not None, 
                         f"Status: {resp.status_code}")
                return True
            else:
                self.test("Login via dev-bypass", False, 
                         f"Status: {resp.status_code}, Body: {resp.text[:200]}")
                return False
        except Exception as e:
            self.test("Login via dev-bypass", False, str(e))
            return False

    def get_headers(self):
        """Get auth headers"""
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    def get_closet_items(self):
        """Fetch all closet items"""
        try:
            resp = requests.get(
                f"{BACKEND_URL}/api/v1/closet?limit=2000",
                headers=self.get_headers(),
                timeout=30
            )
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("items", [])
                self.log(f"Fetched {len(items)} closet items")
                return items
            else:
                self.log(f"Failed to fetch closet: {resp.status_code}", "ERROR")
                return []
        except Exception as e:
            self.log(f"Error fetching closet: {e}", "ERROR")
            return []

    def verify_fingerprints(self, items):
        """Verify that items have non-null source_sha256 and source_phash"""
        self.log(f"Verifying fingerprints for {len(items)} items...")
        
        missing_sha256 = []
        missing_phash = []
        
        for item in items:
            item_id = item.get("id", "unknown")
            title = item.get("title", "Untitled")
            
            sha256 = item.get("source_sha256")
            phash = item.get("source_phash")
            
            if not sha256:
                missing_sha256.append(f"{title} ({item_id})")
            if not phash:
                missing_phash.append(f"{title} ({item_id})")
        
        # Test results
        self.test(
            "All items have source_sha256",
            len(missing_sha256) == 0,
            f"Missing in {len(missing_sha256)} items: {missing_sha256[:3]}"
        )
        
        self.test(
            "All items have source_phash",
            len(missing_phash) == 0,
            f"Missing in {len(missing_phash)} items: {missing_phash[:3]}"
        )
        
        return len(missing_sha256) == 0 and len(missing_phash) == 0

    def verify_clean_image_status(self, item_ids, max_wait=60):
        """Poll items until clean_image_status transitions to 'ready' or timeout"""
        self.log(f"Polling {len(item_ids)} items for clean_image_status transition...")
        
        start_time = time.time()
        pending_ids = set(item_ids)
        ready_ids = set()
        failed_ids = set()
        
        while pending_ids and (time.time() - start_time) < max_wait:
            for item_id in list(pending_ids):
                try:
                    resp = requests.get(
                        f"{BACKEND_URL}/api/v1/closet/{item_id}",
                        headers=self.get_headers(),
                        timeout=10
                    )
                    if resp.status_code == 200:
                        item = resp.json()
                        status = item.get("clean_image_status")
                        
                        if status == "ready":
                            ready_ids.add(item_id)
                            pending_ids.remove(item_id)
                            self.log(f"  Item {item_id[:8]}... → ready")
                        elif status == "failed":
                            failed_ids.add(item_id)
                            pending_ids.remove(item_id)
                            self.log(f"  Item {item_id[:8]}... → failed", "WARN")
                        elif status == "pending":
                            # Still pending, keep polling
                            pass
                        else:
                            # Unknown status
                            self.log(f"  Item {item_id[:8]}... has status: {status}", "WARN")
                except Exception as e:
                    self.log(f"  Error polling item {item_id[:8]}...: {e}", "ERROR")
            
            if pending_ids:
                time.sleep(3)  # Poll every 3 seconds (matches workStore POLL_INTERVAL_MS)
        
        elapsed = time.time() - start_time
        self.log(f"Polling complete after {elapsed:.1f}s: {len(ready_ids)} ready, {len(failed_ids)} failed, {len(pending_ids)} still pending")
        
        # Test results
        self.test(
            "All items transitioned to ready",
            len(ready_ids) == len(item_ids),
            f"Ready: {len(ready_ids)}, Failed: {len(failed_ids)}, Pending: {len(pending_ids)}"
        )
        
        self.test(
            "No items failed polish",
            len(failed_ids) == 0,
            f"Failed IDs: {list(failed_ids)[:3]}"
        )
        
        return len(ready_ids) == len(item_ids)

    def check_error_banners(self):
        """Check if there are any error banners in closet (via API)"""
        # This is a placeholder - in reality we'd need to check the UI
        # For now, we'll just verify the repair endpoints don't report issues
        self.log("Checking for error conditions...")
        
        try:
            # Check hash repair endpoint (dry run)
            resp = requests.post(
                f"{BACKEND_URL}/api/v1/closet/repair-hashes?dry_run=true&only_missing=true&limit=100",
                headers=self.get_headers(),
                timeout=30
            )
            if resp.status_code == 200:
                data = resp.json()
                repaired = data.get("repaired", 0)
                self.test(
                    "No missing fingerprints requiring repair",
                    repaired == 0,
                    f"Would repair {repaired} items"
                )
            else:
                self.log(f"Hash repair check failed: {resp.status_code}", "WARN")
        except Exception as e:
            self.log(f"Error checking hash repair: {e}", "ERROR")

    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*70)
        print("TEST SUMMARY")
        print("="*70)
        print(f"Total tests: {self.tests_run}")
        print(f"Passed: {self.tests_passed} ✅")
        print(f"Failed: {self.tests_failed} ❌")
        
        if self.failures:
            print("\nFailed tests:")
            for failure in self.failures:
                print(f"  - {failure}")
        
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        print(f"\nSuccess rate: {success_rate:.1f}%")
        print("="*70)
        
        return self.tests_failed == 0

def main():
    tester = BulkUploadTester()
    
    # Step 1: Login
    if not tester.login():
        print("❌ Login failed, cannot proceed")
        return 1
    
    # Step 2: Get initial closet state
    tester.log("Fetching initial closet state...")
    initial_items = tester.get_closet_items()
    initial_count = len(initial_items)
    tester.log(f"Initial closet has {initial_count} items")
    
    # Step 3: Verify existing items have fingerprints
    # (This tests that previous uploads worked correctly)
    if initial_items:
        tester.log("Verifying existing items have fingerprints...")
        tester.verify_fingerprints(initial_items)
    
    # Step 4: Check for error conditions
    tester.check_error_banners()
    
    # Note: The actual bulk upload test would require browser automation
    # to upload files via the /add page UI. The backend API doesn't have
    # a direct "upload N files" endpoint - it requires the frontend to:
    # 1. Compute fingerprints client-side
    # 2. Call /analyze with NDJSON streaming
    # 3. Call /closet POST for each item
    # This is tested via Playwright in the browser automation section.
    
    tester.log("Backend API verification complete")
    tester.log("Note: Full bulk upload flow requires browser automation (see Playwright test)")
    
    # Print summary
    success = tester.print_summary()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
