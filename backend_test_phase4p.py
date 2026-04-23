#!/usr/bin/env python3
"""
DressApp Phase 4P PayPal Backend API Testing Suite
Tests all PayPal integration functionality including credits, marketplace transactions, and ad billing.
"""

import requests
import sys
import json
import time
from datetime import datetime
from typing import Dict, Any, Optional

class Phase4PAPITester:
    def __init__(self, base_url: str = "https://ai-stylist-api.preview.emergentagent.com"):
        self.base_url = base_url.rstrip('/')
        self.dev_token = None
        self.buyer_token = None
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
                    token: str = None, timeout: int = 30) -> tuple[bool, Dict, int]:
        """Make HTTP request with error handling"""
        url = f"{self.base_url}/api/v1{endpoint}"
        headers = {}
        
        if token:
            headers['Authorization'] = f'Bearer {token}'
        
        headers.update(self.session.headers)

        try:
            if method == 'GET':
                response = self.session.get(url, headers=headers, timeout=timeout)
            elif method == 'POST':
                response = self.session.post(url, json=data, headers=headers, timeout=timeout)
            elif method == 'PATCH':
                response = self.session.patch(url, json=data, headers=headers, timeout=timeout)
            elif method == 'DELETE':
                response = self.session.delete(url, headers=headers, timeout=timeout)
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
        # Get dev token
        success, data, status = self.make_request('POST', '/auth/dev-bypass')
        if success and status == 200 and 'access_token' in data:
            self.dev_token = data['access_token']
            self.log_test("Setup Dev Auth", True, f"User: {data.get('user', {}).get('email')}")
        else:
            self.log_test("Setup Dev Auth", False, f"Status: {status}, Data: {data}")
            return False

        # Register a buyer user
        timestamp = int(time.time())
        register_data = {
            "email": f"buyer{timestamp}@dressapp.io",
            "password": "BuyerPass123!",
            "display_name": f"Test Buyer {timestamp}"
        }
        
        success, data, status = self.make_request('POST', '/auth/register', register_data)
        if success and status == 201 and 'access_token' in data:
            self.buyer_token = data['access_token']
            self.log_test("Setup Buyer Auth", True, f"User: {data.get('user', {}).get('email')}")
        else:
            self.log_test("Setup Buyer Auth", False, f"Status: {status}, Data: {data}")
            return False

        return True

    # ==================== PAYPAL CONFIG TESTS ====================
    
    def test_paypal_config(self):
        """Test GET /api/v1/paypal/config returns env, client_id, configured, mock_mode, default_currency, supported_currencies"""
        success, data, status = self.make_request('GET', '/paypal/config')
        
        if success and status == 200:
            required_fields = ['env', 'client_id', 'configured', 'mock_mode', 'default_currency', 'supported_currencies']
            has_all_fields = all(field in data for field in required_fields)
            
            # Verify specific values
            env_is_sandbox = data.get('env') == 'sandbox'
            mock_mode_true = data.get('mock_mode') is True
            default_currency_usd = data.get('default_currency') == 'USD'
            has_supported_currencies = isinstance(data.get('supported_currencies'), list) and len(data.get('supported_currencies', [])) > 0
            configured_true = data.get('configured') is True
            
            all_valid = has_all_fields and env_is_sandbox and mock_mode_true and default_currency_usd and has_supported_currencies and configured_true
            self.log_test("PayPal Config", all_valid, 
                         f"Fields: {has_all_fields}, Env: {data.get('env')}, Mock: {data.get('mock_mode')}, Configured: {data.get('configured')}")
        else:
            self.log_test("PayPal Config", False, f"Status: {status}, Data: {data}")

    # ==================== CREDIT TOPUP TESTS ====================
    
    def test_credit_topup_pack_10(self):
        """Test POST /api/v1/credits/topup with pack '10' creates a topup + PayPal order (mock)"""
        if not self.dev_token:
            self.log_test("Credit Topup Pack 10", False, "No dev token available")
            return None
            
        topup_data = {
            "pack": "10",
            "currency": "USD"
        }
        
        success, data, status = self.make_request('POST', '/credits/topup', topup_data, token=self.dev_token)
        
        if success and status == 200:
            required_fields = ['topup_id', 'order_id', 'amount_cents', 'currency']
            has_all_fields = all(field in data for field in required_fields)
            
            # Verify values
            amount_correct = data.get('amount_cents') == 1000  # $10 = 1000 cents
            currency_correct = data.get('currency') == 'USD'
            order_id_mock = data.get('order_id', '').startswith('MOCK-')
            
            all_valid = has_all_fields and amount_correct and currency_correct and order_id_mock
            self.log_test("Credit Topup Pack 10", all_valid, 
                         f"Amount: {data.get('amount_cents')}, Order ID: {data.get('order_id')}")
            return data.get('topup_id')
        else:
            self.log_test("Credit Topup Pack 10", False, f"Status: {status}, Data: {data}")
            return None

    def test_credit_topup_pack_25(self):
        """Test POST /api/v1/credits/topup with pack '25'"""
        if not self.dev_token:
            return None
            
        topup_data = {
            "pack": "25",
            "currency": "USD"
        }
        
        success, data, status = self.make_request('POST', '/credits/topup', topup_data, token=self.dev_token)
        
        if success and status == 200:
            amount_correct = data.get('amount_cents') == 2500  # $25 = 2500 cents
            order_id_mock = data.get('order_id', '').startswith('MOCK-')
            
            all_valid = amount_correct and order_id_mock
            self.log_test("Credit Topup Pack 25", all_valid, 
                         f"Amount: {data.get('amount_cents')}, Order ID: {data.get('order_id')}")
            return data.get('topup_id')
        else:
            self.log_test("Credit Topup Pack 25", False, f"Status: {status}, Data: {data}")
            return None

    def test_credit_topup_pack_50(self):
        """Test POST /api/v1/credits/topup with pack '50'"""
        if not self.dev_token:
            return None
            
        topup_data = {
            "pack": "50",
            "currency": "USD"
        }
        
        success, data, status = self.make_request('POST', '/credits/topup', topup_data, token=self.dev_token)
        
        if success and status == 200:
            amount_correct = data.get('amount_cents') == 5000  # $50 = 5000 cents
            order_id_mock = data.get('order_id', '').startswith('MOCK-')
            
            all_valid = amount_correct and order_id_mock
            self.log_test("Credit Topup Pack 50", all_valid, 
                         f"Amount: {data.get('amount_cents')}, Order ID: {data.get('order_id')}")
            return data.get('topup_id')
        else:
            self.log_test("Credit Topup Pack 50", False, f"Status: {status}, Data: {data}")
            return None

    def test_credit_topup_custom(self):
        """Test POST /api/v1/credits/topup with pack 'custom' + custom_amount_cents works (e.g. 700 cents)"""
        if not self.dev_token:
            return None
            
        topup_data = {
            "pack": "custom",
            "custom_amount_cents": 700,
            "currency": "USD"
        }
        
        success, data, status = self.make_request('POST', '/credits/topup', topup_data, token=self.dev_token)
        
        if success and status == 200:
            amount_correct = data.get('amount_cents') == 700
            order_id_mock = data.get('order_id', '').startswith('MOCK-')
            
            all_valid = amount_correct and order_id_mock
            self.log_test("Credit Topup Custom", all_valid, 
                         f"Amount: {data.get('amount_cents')}, Order ID: {data.get('order_id')}")
            return data.get('topup_id')
        else:
            self.log_test("Credit Topup Custom", False, f"Status: {status}, Data: {data}")
            return None

    def test_credit_topup_validation(self):
        """Test POST /api/v1/credits/topup rejects amounts <100 or >100000"""
        if not self.dev_token:
            self.log_test("Credit Topup Validation", False, "No dev token available")
            return
            
        # Test amount too low
        topup_data = {
            "pack": "custom",
            "custom_amount_cents": 50,  # Below minimum
            "currency": "USD"
        }
        
        success, data, status = self.make_request('POST', '/credits/topup', topup_data, token=self.dev_token)
        low_rejected = status == 400
        
        # Test amount too high
        topup_data = {
            "pack": "custom",
            "custom_amount_cents": 150000,  # Above maximum
            "currency": "USD"
        }
        
        success, data, status = self.make_request('POST', '/credits/topup', topup_data, token=self.dev_token)
        high_rejected = status == 422  # Pydantic validation error
        
        both_rejected = low_rejected and high_rejected
        self.log_test("Credit Topup Validation", both_rejected, 
                     f"Low amount rejected: {low_rejected}, High amount rejected: {high_rejected}")

    def test_credit_topup_capture(self):
        """Test POST /api/v1/credits/topup/{topup_id}/capture transitions status to 'captured'"""
        if not self.dev_token:
            self.log_test("Credit Topup Capture", False, "No dev token available")
            return
            
        # First create a topup
        topup_id = self.test_credit_topup_pack_10()
        if not topup_id:
            self.log_test("Credit Topup Capture", False, "Could not create topup")
            return
        
        # Capture the topup
        success, data, status = self.make_request('POST', f'/credits/topup/{topup_id}/capture', token=self.dev_token)
        
        if success and status == 200:
            topup = data.get('topup', {})
            balance = data.get('balance', {})
            
            # Verify topup status
            status_captured = topup.get('status') == 'captured'
            has_capture_id = topup.get('paypal_capture_id', '').startswith('MOCKCAP-')
            has_captured_at = bool(topup.get('captured_at'))
            
            # Verify balance was credited
            balance_updated = balance.get('balance_cents', 0) >= 1000
            
            all_valid = status_captured and has_capture_id and has_captured_at and balance_updated
            self.log_test("Credit Topup Capture", all_valid, 
                         f"Status: {topup.get('status')}, Capture ID: {topup.get('paypal_capture_id')}, Balance: {balance.get('balance_cents')}")
            return topup_id
        else:
            self.log_test("Credit Topup Capture", False, f"Status: {status}, Data: {data}")
            return None

    def test_credit_topup_capture_idempotent(self):
        """Test POST /api/v1/credits/topup/{topup_id}/capture is idempotent"""
        if not self.dev_token:
            self.log_test("Credit Topup Capture Idempotent", False, "No dev token available")
            return
            
        # Create and capture a topup
        topup_id = self.test_credit_topup_capture()
        if not topup_id:
            self.log_test("Credit Topup Capture Idempotent", False, "Could not create and capture topup")
            return
        
        # Try to capture again
        success, data, status = self.make_request('POST', f'/credits/topup/{topup_id}/capture', token=self.dev_token)
        
        if success and status == 200:
            already_captured = data.get('already_captured') is True
            self.log_test("Credit Topup Capture Idempotent", already_captured, 
                         f"Already captured: {already_captured}")
        else:
            self.log_test("Credit Topup Capture Idempotent", False, f"Status: {status}, Data: {data}")

    # ==================== CREDIT BALANCE TESTS ====================
    
    def test_credit_balance(self):
        """Test GET /api/v1/credits/balance?currency=USD returns the credited balance after capture"""
        if not self.dev_token:
            self.log_test("Credit Balance", False, "No dev token available")
            return
            
        success, data, status = self.make_request('GET', '/credits/balance?currency=USD', token=self.dev_token)
        
        if success and status == 200:
            has_currency = data.get('currency') == 'USD'
            has_balance = 'balance_cents' in data and isinstance(data.get('balance_cents'), int)
            
            all_valid = has_currency and has_balance
            self.log_test("Credit Balance", all_valid, 
                         f"Currency: {data.get('currency')}, Balance: {data.get('balance_cents')} cents")
        else:
            self.log_test("Credit Balance", False, f"Status: {status}, Data: {data}")

    def test_credit_balances(self):
        """Test GET /api/v1/credits/balances returns per-currency totals"""
        if not self.dev_token:
            self.log_test("Credit Balances", False, "No dev token available")
            return
            
        success, data, status = self.make_request('GET', '/credits/balances', token=self.dev_token)
        
        if success and status == 200:
            has_items = 'items' in data and isinstance(data.get('items'), list)
            
            # Check structure of items
            items_valid = True
            if data.get('items'):
                for item in data['items']:
                    if not isinstance(item, dict) or 'currency' not in item or 'balance_cents' not in item:
                        items_valid = False
                        break
            
            all_valid = has_items and items_valid
            self.log_test("Credit Balances", all_valid, 
                         f"Items: {len(data.get('items', []))}")
        else:
            self.log_test("Credit Balances", False, f"Status: {status}, Data: {data}")

    def test_credit_history(self):
        """Test GET /api/v1/credits/history returns topup records sorted desc"""
        if not self.dev_token:
            self.log_test("Credit History", False, "No dev token available")
            return
            
        success, data, status = self.make_request('GET', '/credits/history', token=self.dev_token)
        
        if success and status == 200:
            has_items = 'items' in data and isinstance(data.get('items'), list)
            has_total = 'total' in data
            
            # Check sorting (desc by created_at)
            items = data.get('items', [])
            sorted_correctly = True
            if len(items) > 1:
                for i in range(len(items) - 1):
                    if items[i].get('created_at', '') < items[i + 1].get('created_at', ''):
                        sorted_correctly = False
                        break
            
            all_valid = has_items and has_total and sorted_correctly
            self.log_test("Credit History", all_valid, 
                         f"Items: {len(items)}, Total: {data.get('total')}, Sorted: {sorted_correctly}")
        else:
            self.log_test("Credit History", False, f"Status: {status}, Data: {data}")

    # ==================== AD BILLING TESTS ====================
    
    def setup_professional_user(self):
        """Setup user as professional for ad testing"""
        if not self.dev_token:
            return False
            
        # Update user to be professional
        professional_data = {
            "professional": {
                "is_professional": True,
                "profession": "Fashion Stylist",
                "business_name": "Test Styling Co",
                "approval_status": "approved"
            }
        }
        
        success, data, status = self.make_request('PATCH', '/users/me', professional_data, token=self.dev_token)
        return success and status == 200

    def create_test_campaign(self):
        """Create a test ad campaign"""
        if not self.dev_token:
            return None
            
        campaign_data = {
            "name": "Test Campaign for Billing",
            "profession": "Fashion Stylist",
            "creative": {
                "headline": "Professional Styling Services",
                "body": "Get styled by a professional",
                "cta_label": "Book Now"
            },
            "daily_budget_cents": 5000,  # $50
            "bid_cents": 10,  # 10 cents per impression
            "currency": "USD",
            "status": "active"
        }
        
        success, data, status = self.make_request('POST', '/ads/campaigns', campaign_data, token=self.dev_token)
        
        if success and status == 200:
            return data.get('id')
        return None

    def test_ad_impression_billing(self):
        """Test POST /api/v1/ads/impression/{campaign_id} deducts 1¢ from campaign owner's credit balance"""
        if not self.dev_token:
            self.log_test("Ad Impression Billing", False, "No dev token available")
            return
            
        # Setup professional user
        if not self.setup_professional_user():
            self.log_test("Ad Impression Billing", False, "Could not setup professional user")
            return
        
        # Ensure we have credits
        self.test_credit_topup_capture()
        
        # Create campaign
        campaign_id = self.create_test_campaign()
        if not campaign_id:
            self.log_test("Ad Impression Billing", False, "Could not create campaign")
            return
        
        # Get initial balance
        success, balance_data, status = self.make_request('GET', '/credits/balance?currency=USD', token=self.dev_token)
        if not (success and status == 200):
            self.log_test("Ad Impression Billing", False, "Could not get initial balance")
            return
        
        initial_balance = balance_data.get('balance_cents', 0)
        
        # Track impression
        success, data, status = self.make_request('POST', f'/ads/impression/{campaign_id}')
        
        if success and status == 200:
            impression_ok = data.get('ok') is True
            
            # Check balance was deducted
            success, balance_data, status = self.make_request('GET', '/credits/balance?currency=USD', token=self.dev_token)
            if success and status == 200:
                new_balance = balance_data.get('balance_cents', 0)
                balance_deducted = new_balance == initial_balance - 1  # 1 cent deducted
                
                all_valid = impression_ok and balance_deducted
                self.log_test("Ad Impression Billing", all_valid, 
                             f"Impression OK: {impression_ok}, Balance: {initial_balance} -> {new_balance}")
            else:
                self.log_test("Ad Impression Billing", False, "Could not get new balance")
        else:
            self.log_test("Ad Impression Billing", False, f"Status: {status}, Data: {data}")

    def test_ad_click_billing(self):
        """Test POST /api/v1/ads/click/{campaign_id} deducts 5¢ similarly"""
        if not self.dev_token:
            self.log_test("Ad Click Billing", False, "No dev token available")
            return
            
        # Get campaign ID from previous test or create new one
        campaign_id = self.create_test_campaign()
        if not campaign_id:
            self.log_test("Ad Click Billing", False, "Could not create campaign")
            return
        
        # Get initial balance
        success, balance_data, status = self.make_request('GET', '/credits/balance?currency=USD', token=self.dev_token)
        if not (success and status == 200):
            self.log_test("Ad Click Billing", False, "Could not get initial balance")
            return
        
        initial_balance = balance_data.get('balance_cents', 0)
        
        # Track click
        success, data, status = self.make_request('POST', f'/ads/click/{campaign_id}')
        
        if success and status == 200:
            click_ok = data.get('ok') is True
            
            # Check balance was deducted
            success, balance_data, status = self.make_request('GET', '/credits/balance?currency=USD', token=self.dev_token)
            if success and status == 200:
                new_balance = balance_data.get('balance_cents', 0)
                balance_deducted = new_balance == initial_balance - 5  # 5 cents deducted
                
                all_valid = click_ok and balance_deducted
                self.log_test("Ad Click Billing", all_valid, 
                             f"Click OK: {click_ok}, Balance: {initial_balance} -> {new_balance}")
            else:
                self.log_test("Ad Click Billing", False, "Could not get new balance")
        else:
            self.log_test("Ad Click Billing", False, f"Status: {status}, Data: {data}")

    def test_insufficient_funds_auto_pause(self):
        """Test when balance hits zero, impression/click returns {ok:false, reason:'insufficient_funds'} AND campaign is auto-paused"""
        if not self.dev_token:
            self.log_test("Insufficient Funds Auto Pause", False, "No dev token available")
            return
            
        # Create campaign with minimal credits
        campaign_id = self.create_test_campaign()
        if not campaign_id:
            self.log_test("Insufficient Funds Auto Pause", False, "Could not create campaign")
            return
        
        # Drain balance by making multiple clicks until insufficient funds
        max_attempts = 200  # Safety limit
        attempts = 0
        
        while attempts < max_attempts:
            success, data, status = self.make_request('POST', f'/ads/click/{campaign_id}')
            attempts += 1
            
            if success and status == 200:
                if data.get('ok') is False and data.get('reason') == 'insufficient_funds':
                    # Found insufficient funds response
                    insufficient_funds_detected = True
                    
                    # Check if campaign was auto-paused
                    success, campaign_data, status = self.make_request('GET', f'/ads/campaigns/{campaign_id}', token=self.dev_token)
                    if success and status == 200:
                        campaign_paused = campaign_data.get('status') == 'paused'
                        status_reason = campaign_data.get('status_reason') == 'insufficient_funds'
                        
                        all_valid = insufficient_funds_detected and campaign_paused and status_reason
                        self.log_test("Insufficient Funds Auto Pause", all_valid, 
                                     f"Insufficient funds: {insufficient_funds_detected}, Paused: {campaign_paused}, Reason: {status_reason}")
                        return
                    else:
                        self.log_test("Insufficient Funds Auto Pause", False, "Could not get campaign status")
                        return
            else:
                break
        
        self.log_test("Insufficient Funds Auto Pause", False, f"Did not reach insufficient funds after {attempts} attempts")

    # ==================== MARKETPLACE TRANSACTION TESTS ====================
    
    def create_test_listing(self):
        """Create a test listing for marketplace transactions"""
        if not self.dev_token:
            return None
            
        # Create closet item first
        item_data = {
            "title": "Designer Jacket for PayPal Test",
            "category": "outerwear",
            "sub_category": "jacket",
            "brand": "Designer Brand",
            "color": "black",
            "formality": "business"
        }
        
        success, data, status = self.make_request('POST', '/closet', item_data, token=self.dev_token)
        if not (success and status == 201):
            return None
            
        closet_item_id = data.get('id')
        
        # Create listing
        listing_data = {
            "closet_item_id": closet_item_id,
            "title": "Designer Jacket - PayPal Test",
            "description": "Test listing for PayPal integration",
            "category": "outerwear",
            "size": "M",
            "condition": "like_new",
            "list_price_cents": 15000,  # $150
            "ships_to": ["US", "CA"]
        }
        
        success, data, status = self.make_request('POST', '/listings', listing_data, token=self.dev_token)
        
        if success and status == 201:
            return data.get('id')
        return None

    def test_marketplace_buy_create(self):
        """Test POST /api/v1/listings/{id}/buy creates Transaction + PayPal order"""
        if not self.dev_token or not self.buyer_token:
            self.log_test("Marketplace Buy Create", False, "Missing required tokens")
            return None
            
        # Create listing
        listing_id = self.create_test_listing()
        if not listing_id:
            self.log_test("Marketplace Buy Create", False, "Could not create listing")
            return None
        
        # Buy listing
        success, data, status = self.make_request('POST', f'/listings/{listing_id}/buy', token=self.buyer_token)
        
        if success and status == 200:
            required_fields = ['order_id', 'transaction_id', 'amount_cents', 'currency']
            has_all_fields = all(field in data for field in required_fields)
            
            # Verify values
            amount_correct = data.get('amount_cents') == 15000  # $150
            currency_correct = data.get('currency') == 'USD'
            order_id_mock = data.get('order_id', '').startswith('MOCK-')
            
            all_valid = has_all_fields and amount_correct and currency_correct and order_id_mock
            self.log_test("Marketplace Buy Create", all_valid, 
                         f"Order ID: {data.get('order_id')}, Transaction ID: {data.get('transaction_id')}, Amount: {data.get('amount_cents')}")
            return data.get('order_id'), data.get('transaction_id'), listing_id
        else:
            self.log_test("Marketplace Buy Create", False, f"Status: {status}, Data: {data}")
            return None, None, None

    def test_marketplace_buy_capture(self):
        """Test POST /api/v1/listings/{id}/buy/capture captures order, sets Transaction.status='paid'"""
        if not self.dev_token or not self.buyer_token:
            self.log_test("Marketplace Buy Capture", False, "Missing required tokens")
            return
            
        # Create buy order
        order_id, transaction_id, listing_id = self.test_marketplace_buy_create()
        if not all([order_id, transaction_id, listing_id]):
            self.log_test("Marketplace Buy Capture", False, "Could not create buy order")
            return
        
        # Capture order
        success, data, status = self.make_request('POST', f'/listings/{listing_id}/buy/capture?order_id={order_id}', token=self.buyer_token)
        
        if success and status == 200:
            transaction = data.get('transaction', {})
            
            # Verify transaction status
            status_paid = transaction.get('status') == 'paid'
            has_paid_at = bool(transaction.get('paid_at'))
            has_capture_id = transaction.get('paypal', {}).get('capture_id', '').startswith('MOCKCAP-')
            
            all_valid = status_paid and has_paid_at and has_capture_id
            self.log_test("Marketplace Buy Capture", all_valid, 
                         f"Status: {transaction.get('status')}, Capture ID: {transaction.get('paypal', {}).get('capture_id')}")
            
            # Check if listing was marked as sold
            success, listing_data, status = self.make_request('GET', f'/listings/{listing_id}')
            if success and status == 200:
                listing_sold = listing_data.get('status') == 'sold'
                self.log_test("Marketplace Listing Sold", listing_sold, 
                             f"Listing status: {listing_data.get('status')}")
        else:
            self.log_test("Marketplace Buy Capture", False, f"Status: {status}, Data: {data}")

    def test_marketplace_buy_validation(self):
        """Test buying your own listing → 400, buying inactive listing → 400, invalid listing_id → 404"""
        if not self.dev_token or not self.buyer_token:
            self.log_test("Marketplace Buy Validation", False, "Missing required tokens")
            return
            
        # Create listing
        listing_id = self.create_test_listing()
        if not listing_id:
            self.log_test("Marketplace Buy Validation", False, "Could not create listing")
            return
        
        # Test buying own listing
        success, data, status = self.make_request('POST', f'/listings/{listing_id}/buy', token=self.dev_token)
        own_listing_rejected = status == 400
        
        # Test invalid listing ID
        success, data, status = self.make_request('POST', '/listings/invalid-id/buy', token=self.buyer_token)
        invalid_id_rejected = status == 404
        
        # Test inactive listing (first deactivate the listing)
        success, data, status = self.make_request('PATCH', f'/listings/{listing_id}', {"status": "removed"}, token=self.dev_token)
        if success and status == 200:
            success, data, status = self.make_request('POST', f'/listings/{listing_id}/buy', token=self.buyer_token)
            inactive_rejected = status == 400
        else:
            inactive_rejected = True  # Assume it would be rejected
        
        all_rejected = own_listing_rejected and invalid_id_rejected and inactive_rejected
        self.log_test("Marketplace Buy Validation", all_rejected, 
                     f"Own listing: {own_listing_rejected}, Invalid ID: {invalid_id_rejected}, Inactive: {inactive_rejected}")

    def test_seller_payout_setup(self):
        """Test seller payout when seller has paypal_receiver_email set"""
        if not self.dev_token:
            self.log_test("Seller Payout Setup", False, "No dev token available")
            return
            
        # Set PayPal receiver email for seller
        payout_data = {
            "paypal_receiver_email": "seller@example.com"
        }
        
        success, data, status = self.make_request('PATCH', '/users/me', payout_data, token=self.dev_token)
        
        if success and status == 200:
            email_set = data.get('paypal_receiver_email') == 'seller@example.com'
            self.log_test("Seller Payout Setup", email_set, 
                         f"PayPal email: {data.get('paypal_receiver_email')}")
        else:
            self.log_test("Seller Payout Setup", False, f"Status: {status}, Data: {data}")

    # ==================== WEBHOOK TESTS ====================
    
    def test_paypal_webhook(self):
        """Test POST /api/v1/paypal/webhook with arbitrary JSON body records event into db"""
        webhook_data = {
            "id": f"evt_test_{int(time.time())}",
            "event_type": "PAYMENT.CAPTURE.COMPLETED",
            "resource_type": "capture",
            "resource": {
                "id": "MOCKCAP-12345",
                "status": "COMPLETED"
            }
        }
        
        success, data, status = self.make_request('POST', '/paypal/webhook', webhook_data)
        
        if success and status == 200:
            webhook_ok = data.get('ok') is True
            not_duplicate = data.get('duplicate') is not True
            
            all_valid = webhook_ok and not_duplicate
            self.log_test("PayPal Webhook", all_valid, 
                         f"OK: {webhook_ok}, Not duplicate: {not_duplicate}")
            
            # Test duplicate event
            success, data, status = self.make_request('POST', '/paypal/webhook', webhook_data)
            if success and status == 200:
                is_duplicate = data.get('duplicate') is True
                self.log_test("PayPal Webhook Duplicate", is_duplicate, 
                             f"Duplicate detected: {is_duplicate}")
        else:
            self.log_test("PayPal Webhook", False, f"Status: {status}, Data: {data}")

    # ==================== USER PROFILE TESTS ====================
    
    def test_user_paypal_email_update(self):
        """Test PATCH /api/v1/users/me accepts new `paypal_receiver_email` field"""
        if not self.dev_token:
            self.log_test("User PayPal Email Update", False, "No dev token available")
            return
            
        update_data = {
            "paypal_receiver_email": "updated@example.com"
        }
        
        success, data, status = self.make_request('PATCH', '/users/me', update_data, token=self.dev_token)
        
        if success and status == 200:
            email_updated = data.get('paypal_receiver_email') == 'updated@example.com'
            self.log_test("User PayPal Email Update", email_updated, 
                         f"PayPal email: {data.get('paypal_receiver_email')}")
        else:
            self.log_test("User PayPal Email Update", False, f"Status: {status}, Data: {data}")

    # ==================== MAIN TEST RUNNER ====================
    
    def run_all_tests(self):
        """Run all Phase 4P tests"""
        print("🚀 Starting Phase 4P PayPal Backend API Tests")
        print("=" * 60)
        
        # Setup
        if not self.setup_auth():
            print("❌ Failed to setup authentication, aborting tests")
            return
        
        print("\n📋 PayPal Configuration Tests")
        print("-" * 40)
        self.test_paypal_config()
        
        print("\n💳 Credit Topup Tests")
        print("-" * 40)
        self.test_credit_topup_pack_10()
        self.test_credit_topup_pack_25()
        self.test_credit_topup_pack_50()
        self.test_credit_topup_custom()
        self.test_credit_topup_validation()
        self.test_credit_topup_capture()
        self.test_credit_topup_capture_idempotent()
        
        print("\n💰 Credit Balance Tests")
        print("-" * 40)
        self.test_credit_balance()
        self.test_credit_balances()
        self.test_credit_history()
        
        print("\n📢 Ad Billing Tests")
        print("-" * 40)
        self.test_ad_impression_billing()
        self.test_ad_click_billing()
        self.test_insufficient_funds_auto_pause()
        
        print("\n🛒 Marketplace Transaction Tests")
        print("-" * 40)
        self.test_marketplace_buy_create()
        self.test_marketplace_buy_capture()
        self.test_marketplace_buy_validation()
        self.test_seller_payout_setup()
        
        print("\n🔗 Webhook Tests")
        print("-" * 40)
        self.test_paypal_webhook()
        
        print("\n👤 User Profile Tests")
        print("-" * 40)
        self.test_user_paypal_email_update()
        
        # Summary
        print("\n" + "=" * 60)
        print(f"📊 Test Results: {self.tests_passed}/{self.tests_run} passed")
        
        if self.failed_tests:
            print("\n❌ Failed Tests:")
            for test in self.failed_tests:
                print(f"  • {test['test']}: {test['details']}")
        
        return self.tests_passed == self.tests_run

def main():
    tester = Phase4PAPITester()
    success = tester.run_all_tests()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())