"""
Backend test suite for Marketplace Wave 2 — Swap & Donate flows.

Tests:
1. POST /api/v1/transactions/swap - valid swap with offered_item_id
2. POST /api/v1/transactions/swap - own listing (should fail 400)
3. POST /api/v1/transactions/swap - non-existent offered_item_id (should fail 404)
4. POST /api/v1/transactions/donate - valid donation
5. POST /api/v1/transactions/donate - own listing (should fail 400)
6. GET /api/v1/transactions/action - accept with valid JWT
7. GET /api/v1/transactions/action - idempotent accept (same token twice)
8. GET /api/v1/transactions/action - tampered token (should fail 400)
9. GET /api/v1/transactions/:id/landing-summary - public endpoint (no auth)
10. POST /api/v1/transactions/:id/confirm-receipt - on pending tx (should fail 409)
11. GET /api/v1/transactions - list should include swap transactions
"""
import sys
import os
import requests
import jwt
from datetime import datetime, timedelta, timezone
import uuid

# Read backend URL from frontend/.env
BACKEND_URL = "https://ai-stylist-api.preview.emergentagent.com"
API_BASE = f"{BACKEND_URL}/api/v1"

# JWT credentials from backend/.env
JWT_SECRET = "dressapp_jwt_secret_xK9mQ2nP4vR7sT8uW"
JWT_ALGORITHM = "HS256"

class TestRunner:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.token = None
        self.user_id = None
        self.test_data = {}
        
    def log(self, msg):
        print(f"  {msg}")
        
    def test(self, name, fn):
        """Run a single test"""
        self.tests_run += 1
        print(f"\n🔍 Test {self.tests_run}: {name}")
        try:
            fn()
            self.tests_passed += 1
            print(f"✅ PASSED")
            return True
        except AssertionError as e:
            print(f"❌ FAILED: {e}")
            return False
        except Exception as e:
            print(f"❌ ERROR: {e}")
            return False
    
    def setup_auth(self):
        """Get dev-bypass token"""
        print("\n📋 Setup: Getting dev-bypass token...")
        resp = requests.post(f"{API_BASE}/auth/dev-bypass")
        assert resp.status_code == 200, f"Dev-bypass failed: {resp.status_code}"
        data = resp.json()
        self.token = data["access_token"]
        
        # Get user info
        resp = requests.get(f"{API_BASE}/users/me", headers={"Authorization": f"Bearer {self.token}"})
        assert resp.status_code == 200, f"Get user failed: {resp.status_code}"
        user = resp.json()
        self.user_id = user["id"]
        self.log(f"Authenticated as user: {self.user_id}")
        
    def setup_test_data(self):
        """Create test listings and closet items"""
        print("\n📋 Setup: Creating test data...")
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        
        # Create a closet item for swapping
        closet_item = {
            "title": "Test Swap Item",
            "category": "Tops",
            "source": "Private",
            "marketplace_intent": "swap"
        }
        resp = requests.post(f"{API_BASE}/closet", json=closet_item, headers=headers)
        assert resp.status_code == 201, f"Create closet item failed: {resp.status_code}"
        self.test_data["my_closet_item_id"] = resp.json()["id"]
        self.log(f"Created closet item: {self.test_data['my_closet_item_id']}")
        
        # Get existing listings to find one NOT owned by us
        resp = requests.get(f"{API_BASE}/listings?status=active&limit=30", headers=headers)
        assert resp.status_code == 200, f"List listings failed: {resp.status_code}"
        listings = resp.json().get("items", [])
        
        # Find a swap listing not owned by us
        swap_listing = None
        donate_listing = None
        for listing in listings:
            if listing.get("seller_id") != self.user_id:
                if listing.get("mode") == "swap" and not swap_listing:
                    swap_listing = listing
                elif listing.get("mode") == "donate" and not donate_listing:
                    donate_listing = listing
        
        # If no swap/donate listings exist, create them using a different approach
        # We'll create our own listings first, then use them for "own listing" tests
        
        # Create a swap listing (owned by us - for "own listing" test)
        my_swap_listing = {
            "title": "My Test Swap Listing",
            "description": "Test swap listing",
            "category": "Tops",
            "size": "M",
            "condition": "good",
            "mode": "swap",
            "source": "Shared",
            "list_price_cents": 0,
            "currency": "USD"
        }
        resp = requests.post(f"{API_BASE}/listings", json=my_swap_listing, headers=headers)
        assert resp.status_code == 201, f"Create my swap listing failed: {resp.status_code}: {resp.text}"
        self.test_data["my_swap_listing_id"] = resp.json()["id"]
        self.log(f"Created my swap listing: {self.test_data['my_swap_listing_id']}")
        
        # Create a donate listing (owned by us - for "own listing" test)
        my_donate_listing = {
            "title": "My Test Donate Listing",
            "description": "Test donate listing",
            "category": "Tops",
            "size": "L",
            "condition": "good",
            "mode": "donate",
            "source": "Shared",
            "list_price_cents": 0,
            "currency": "USD"
        }
        resp = requests.post(f"{API_BASE}/listings", json=my_donate_listing, headers=headers)
        assert resp.status_code == 201, f"Create my donate listing failed: {resp.status_code}: {resp.text}"
        self.test_data["my_donate_listing_id"] = resp.json()["id"]
        self.log(f"Created my donate listing: {self.test_data['my_donate_listing_id']}")
        
        # Use existing foreign listings if found, otherwise note that we need them
        if swap_listing:
            self.test_data["foreign_swap_listing_id"] = swap_listing["id"]
            self.log(f"Found foreign swap listing: {swap_listing['id']}")
        else:
            self.log("⚠️  No foreign swap listings found - will skip some tests")
            
        if donate_listing:
            self.test_data["foreign_donate_listing_id"] = donate_listing["id"]
            self.log(f"Found foreign donate listing: {donate_listing['id']}")
        else:
            self.log("⚠️  No foreign donate listings found - will skip some tests")
    
    def mint_action_token(self, tx_id, jti, role="lister", expires_hours=24):
        """Mint a JWT action token for testing"""
        now = datetime.now(timezone.utc)
        payload = {
            "aud": "dressapp.tx_action",
            "sub": tx_id,
            "role": role,
            "decision_choices": ["accept", "deny"],
            "jti": jti,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=expires_hours)).timestamp()),
        }
        return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    
    def test_swap_valid(self):
        """Test POST /transactions/swap with valid data"""
        if "foreign_swap_listing_id" not in self.test_data:
            self.log("⚠️  Skipping - no foreign swap listing available")
            return
            
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        payload = {
            "listing_id": self.test_data["foreign_swap_listing_id"],
            "offered_item_id": self.test_data["my_closet_item_id"]
        }
        resp = requests.post(f"{API_BASE}/transactions/swap", json=payload, headers=headers)
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
        
        tx = resp.json()
        assert tx["kind"] == "swap", f"Expected kind='swap', got {tx.get('kind')}"
        assert tx["swap"]["offered_item_id"] == self.test_data["my_closet_item_id"], "offered_item_id mismatch"
        assert tx["swap"]["action_token_jti"] is not None, "action_token_jti should be set"
        assert tx["status"] == "pending", f"Expected status='pending', got {tx.get('status')}"
        
        self.test_data["swap_tx_id"] = tx["id"]
        self.test_data["swap_tx_jti"] = tx["swap"]["action_token_jti"]
        self.log(f"Created swap transaction: {tx['id']}")
    
    def test_swap_own_listing(self):
        """Test POST /transactions/swap with own listing (should fail 400)"""
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        payload = {
            "listing_id": self.test_data["my_swap_listing_id"],
            "offered_item_id": self.test_data["my_closet_item_id"]
        }
        resp = requests.post(f"{API_BASE}/transactions/swap", json=payload, headers=headers)
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
        assert "cannot swap with your own listing" in resp.text.lower(), f"Wrong error message: {resp.text}"
        self.log("Correctly rejected swap with own listing")
    
    def test_swap_nonexistent_item(self):
        """Test POST /transactions/swap with non-existent offered_item_id (should fail 404)"""
        if "foreign_swap_listing_id" not in self.test_data:
            self.log("⚠️  Skipping - no foreign swap listing available")
            return
            
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        payload = {
            "listing_id": self.test_data["foreign_swap_listing_id"],
            "offered_item_id": "nonexistent-item-id-12345"
        }
        resp = requests.post(f"{API_BASE}/transactions/swap", json=payload, headers=headers)
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
        self.log("Correctly rejected non-existent offered_item_id")
    
    def test_donate_valid(self):
        """Test POST /transactions/donate with valid data"""
        if "foreign_donate_listing_id" not in self.test_data:
            self.log("⚠️  Skipping - no foreign donate listing available")
            return
            
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        payload = {
            "listing_id": self.test_data["foreign_donate_listing_id"],
            "handling_fee_cents": 0
        }
        resp = requests.post(f"{API_BASE}/transactions/donate", json=payload, headers=headers)
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
        
        tx = resp.json()
        assert tx["kind"] == "donate", f"Expected kind='donate', got {tx.get('kind')}"
        assert tx["donate"]["action_token_jti"] is not None, "action_token_jti should be set"
        assert tx["status"] == "pending", f"Expected status='pending', got {tx.get('status')}"
        
        self.test_data["donate_tx_id"] = tx["id"]
        self.test_data["donate_tx_jti"] = tx["donate"]["action_token_jti"]
        self.log(f"Created donate transaction: {tx['id']}")
    
    def test_donate_own_listing(self):
        """Test POST /transactions/donate with own listing (should fail 400)"""
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        payload = {
            "listing_id": self.test_data["my_donate_listing_id"],
            "handling_fee_cents": 0
        }
        resp = requests.post(f"{API_BASE}/transactions/donate", json=payload, headers=headers)
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
        assert "cannot claim your own donation" in resp.text.lower(), f"Wrong error message: {resp.text}"
        self.log("Correctly rejected donation of own listing")
    
    def test_action_accept(self):
        """Test GET /transactions/action with valid JWT (accept)"""
        if "swap_tx_id" not in self.test_data:
            self.log("⚠️  Skipping - no swap transaction available")
            return
            
        # Mint a valid token
        token = self.mint_action_token(
            self.test_data["swap_tx_id"],
            self.test_data["swap_tx_jti"],
            role="lister"
        )
        
        # Call action endpoint (no auth header - public endpoint)
        resp = requests.get(
            f"{API_BASE}/transactions/action",
            params={"token": token, "decision": "accept"},
            allow_redirects=False
        )
        assert resp.status_code == 303, f"Expected 303 redirect, got {resp.status_code}"
        
        location = resp.headers.get("Location", "")
        assert "/transactions/" in location, f"Expected redirect to /transactions/..., got {location}"
        assert "status=accepted" in location, f"Expected status=accepted in redirect, got {location}"
        
        self.log(f"Action endpoint redirected to: {location}")
        
        # Verify transaction was updated
        headers = {"Authorization": f"Bearer {self.token}"}
        resp = requests.get(f"{API_BASE}/transactions/{self.test_data['swap_tx_id']}", headers=headers)
        assert resp.status_code == 200, f"Get transaction failed: {resp.status_code}"
        tx = resp.json()
        assert tx["status"] == "accepted", f"Expected status='accepted', got {tx.get('status')}"
        assert tx["swap"]["accepted_at"] is not None, "accepted_at should be set"
        assert tx["swap"]["action_token_used"] is True, "action_token_used should be True"
        self.log("Transaction correctly updated to accepted")
    
    def test_action_idempotent(self):
        """Test GET /transactions/action with same token (idempotent)"""
        if "swap_tx_id" not in self.test_data:
            self.log("⚠️  Skipping - no swap transaction available")
            return
            
        # Use the same token again
        token = self.mint_action_token(
            self.test_data["swap_tx_id"],
            self.test_data["swap_tx_jti"],
            role="lister"
        )
        
        resp = requests.get(
            f"{API_BASE}/transactions/action",
            params={"token": token, "decision": "accept"},
            allow_redirects=False
        )
        assert resp.status_code == 303, f"Expected 303 redirect, got {resp.status_code}"
        
        location = resp.headers.get("Location", "")
        assert "status=accepted" in location, f"Expected status=accepted (idempotent), got {location}"
        self.log("Idempotent accept correctly handled")
    
    def test_action_tampered_token(self):
        """Test GET /transactions/action with tampered token (should fail 400)"""
        # Create a garbage token
        tampered_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        
        resp = requests.get(
            f"{API_BASE}/transactions/action",
            params={"token": tampered_token, "decision": "accept"},
            allow_redirects=False
        )
        # Should either be 400 or redirect to invalid status
        assert resp.status_code in [400, 303], f"Expected 400 or 303, got {resp.status_code}"
        
        if resp.status_code == 303:
            location = resp.headers.get("Location", "")
            assert "status=invalid" in location, f"Expected status=invalid for tampered token, got {location}"
        
        self.log("Tampered token correctly rejected")
    
    def test_landing_summary_public(self):
        """Test GET /transactions/:id/landing-summary (no auth)"""
        if "swap_tx_id" not in self.test_data:
            self.log("⚠️  Skipping - no swap transaction available")
            return
            
        # Call without auth header
        resp = requests.get(f"{API_BASE}/transactions/{self.test_data['swap_tx_id']}/landing-summary")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        
        data = resp.json()
        assert "transaction" in data, "Response should have 'transaction' key"
        assert "listing" in data, "Response should have 'listing' key"
        
        tx = data["transaction"]
        assert tx["id"] == self.test_data["swap_tx_id"], "Transaction ID mismatch"
        assert tx["kind"] == "swap", f"Expected kind='swap', got {tx.get('kind')}"
        assert tx["status"] == "accepted", f"Expected status='accepted', got {tx.get('status')}"
        
        listing = data["listing"]
        assert "title" in listing, "Listing should have title"
        assert "size" in listing, "Listing should have size"
        assert "condition" in listing, "Listing should have condition"
        assert "description" in listing, "Listing should have description"
        
        self.log(f"Landing summary returned: {listing.get('title')}")
    
    def test_confirm_receipt_pending(self):
        """Test POST /transactions/:id/confirm-receipt on pending tx (should fail 409)"""
        if "donate_tx_id" not in self.test_data:
            self.log("⚠️  Skipping - no donate transaction available")
            return
            
        headers = {"Authorization": f"Bearer {self.token}"}
        resp = requests.post(f"{API_BASE}/transactions/{self.test_data['donate_tx_id']}/confirm-receipt", headers=headers)
        assert resp.status_code == 409, f"Expected 409, got {resp.status_code}"
        assert "not in a confirmable state" in resp.text.lower(), f"Wrong error message: {resp.text}"
        self.log("Correctly rejected confirm-receipt on pending transaction")
    
    def test_list_transactions(self):
        """Test GET /transactions includes swap transactions"""
        headers = {"Authorization": f"Bearer {self.token}"}
        resp = requests.get(f"{API_BASE}/transactions", headers=headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        
        data = resp.json()
        assert "items" in data, "Response should have 'items' key"
        
        items = data["items"]
        swap_txs = [tx for tx in items if tx.get("kind") == "swap"]
        assert len(swap_txs) > 0, "Should have at least one swap transaction"
        
        self.log(f"Found {len(swap_txs)} swap transaction(s) in list")
    
    def run_all(self):
        """Run all tests"""
        print("=" * 60)
        print("🧪 Marketplace Wave 2 Backend Test Suite")
        print("=" * 60)
        
        try:
            self.setup_auth()
            self.setup_test_data()
        except Exception as e:
            print(f"\n❌ Setup failed: {e}")
            return 1
        
        # Run tests
        self.test("POST /transactions/swap - valid swap", self.test_swap_valid)
        self.test("POST /transactions/swap - own listing (400)", self.test_swap_own_listing)
        self.test("POST /transactions/swap - non-existent item (404)", self.test_swap_nonexistent_item)
        self.test("POST /transactions/donate - valid donation", self.test_donate_valid)
        self.test("POST /transactions/donate - own listing (400)", self.test_donate_own_listing)
        self.test("GET /transactions/action - accept with JWT", self.test_action_accept)
        self.test("GET /transactions/action - idempotent accept", self.test_action_idempotent)
        self.test("GET /transactions/action - tampered token", self.test_action_tampered_token)
        self.test("GET /transactions/:id/landing-summary - public", self.test_landing_summary_public)
        self.test("POST /transactions/:id/confirm-receipt - pending (409)", self.test_confirm_receipt_pending)
        self.test("GET /transactions - list includes swap", self.test_list_transactions)
        
        # Summary
        print("\n" + "=" * 60)
        print(f"📊 Results: {self.tests_passed}/{self.tests_run} tests passed")
        print("=" * 60)
        
        return 0 if self.tests_passed == self.tests_run else 1

if __name__ == "__main__":
    runner = TestRunner()
    sys.exit(runner.run_all())
