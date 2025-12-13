# test_simple.py
import requests

BASE_URL = "http://localhost:8000"
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiZmMxMjZhODItNDFjNi00ZjQ4LWE1MGMtYzEzZTBiM2M4YjE5IiwiZW1haWwiOiJ0ZWFtc29yYTQwQGdtYWlsLmNvbSIsInJvbGUiOiJWRU5ERVVSIiwiZnVsbF9uYW1lIjoiSmVhbiBSYXltb25kIiwiZXhwIjoxNzY1MTc5NzIyLCJpYXQiOjE3NjUxNzYxMjIsIm5iZiI6MTc2NTE3NjEyMn0.R-YSmWkq56jMLbm1162YrYftt7xFPgLtJkuNC68m2FE"

headers = {"Authorization": f"Bearer {TOKEN}"}

print("🎯 TEST RAPIDE APRÈS CORRECTION DE L'ORDRE")
print("=" * 60)

endpoints = [
    ("GET", "/products/debug/current-seller"),
    ("GET", "/products/search?q=produit"),
    ("GET", "/products/filter?seller_id=53ee0b71-dc52-448c-b265-e4b776dbbab2"),
    ("POST", "/products/generate-code")
]

for method, endpoint in endpoints:
    print(f"\n{method} {endpoint}")
    
    if method == "POST" and "generate-code" in endpoint:
        data = {
            "category_name": "Automobile",
            "seller_id": "53ee0b71-dc52-448c-b265-e4b776dbbab2"
        }
        response = requests.post(f"{BASE_URL}{endpoint}", json=data, headers=headers)
    else:
        response = requests.get(f"{BASE_URL}{endpoint}", headers=headers)
    
    print(f"   Status: {response.status_code}")
    
    if response.status_code == 200:
        print(f"   ✅ SUCCESS")
    elif response.status_code == 422:
        print(f"   ❌ VALIDATION ERROR: {response.text}")
    elif response.status_code == 405:
        print(f"   ❌ METHOD NOT ALLOWED")
    else:
        print(f"   ❌ ERROR: {response.text}")

print("\n" + "=" * 60)
print("✅ Si tout est vert, ton backend est COMPLÈTEMENT FIXÉ !")