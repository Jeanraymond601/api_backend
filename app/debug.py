import requests

def test_debug():
    """Test rapide pour voir les routes"""
    response = requests.get("http://localhost:8000/debug/routes")
    if response.status_code == 200:
        data = response.json()
        print("Routes d'authentification disponibles:")
        for route in data.get('routes', []):
            path = route['path']
            if any(keyword in path for keyword in ['auth', 'register', 'login']):
                print(f"  {route['methods']} {path}")

if __name__ == "__main__":
    test_debug()