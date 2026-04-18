#!/usr/bin/env python3
"""Debug stylist form data issue with detailed logging"""

import requests

# Get dev token first
base_url = "https://ai-stylist-api.preview.emergentagent.com"
response = requests.post(f"{base_url}/api/v1/auth/dev-bypass")
token = response.json()['access_token']

# Test stylist with form data - detailed debugging
headers = {'Authorization': f'Bearer {token}'}
data = {'text': 'What should I wear today?'}

print("Testing stylist with form data...")
print(f"URL: {base_url}/api/v1/stylist")
print(f"Headers: {headers}")
print(f"Data: {data}")

# Use requests directly to see what's happening
response = requests.post(f"{base_url}/api/v1/stylist", data=data, headers=headers)
print(f"Status: {response.status_code}")
print(f"Response headers: {response.headers}")
print(f"Response: {response.text}")

# Also test with files parameter
print("\n--- Testing with files parameter ---")
files = {'text': (None, 'What should I wear today?')}
response2 = requests.post(f"{base_url}/api/v1/stylist", files=files, headers=headers)
print(f"Status: {response2.status_code}")
print(f"Response: {response2.text}")