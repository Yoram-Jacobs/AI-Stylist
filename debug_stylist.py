#!/usr/bin/env python3
"""Debug stylist form data issue"""

import requests

# Get dev token first
base_url = "https://ai-stylist-api.preview.emergentagent.com"
response = requests.post(f"{base_url}/api/v1/auth/dev-bypass")
token = response.json()['access_token']

# Test stylist with form data
headers = {'Authorization': f'Bearer {token}'}
data = {'text': 'What should I wear today?'}

print("Testing stylist with form data...")
print(f"Headers: {headers}")
print(f"Data: {data}")

response = requests.post(f"{base_url}/api/v1/stylist", data=data, headers=headers)
print(f"Status: {response.status_code}")
print(f"Response: {response.text}")