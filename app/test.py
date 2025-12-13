import requests
import json

# Configuration
BASE_URL = "http://localhost:8000"
EMAIL = "teamsora40@gmail.com"
PASSWORD = "Team@123"

def get_jwt_token():
    """Obtenir un token JWT depuis l'API"""
    url = f"{BASE_URL}/auth/login"
    
    payload = {
        "email": EMAIL,
        "password": PASSWORD
    }
    
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        
        data = response.json()
        
        if "access_token" in data:
            token = data["access_token"]
            print(f"✅ Token obtenu avec succès!")
            print(f"Token: {token[:50]}...")
            return token
        else:
            print(f"❌ Token non trouvé dans la réponse")
            print(f"Réponse: {data}")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Erreur lors de la requête: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Status code: {e.response.status_code}")
            print(f"Réponse: {e.response.text}")
        return None

def test_token(token):
    """Tester le token avec une requête API"""
    if not token:
        print("❌ Aucun token à tester")
        return
    
    url = f"{BASE_URL}/products/seller/my-products"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(url, headers=headers)
        
        print(f"\n=== TEST DU TOKEN ===")
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Token valide!")
            print(f"Nombre de produits: {len(data)}")
            return True
        else:
            print(f"❌ Token invalide ou erreur API")
            print(f"Réponse: {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Erreur lors du test: {e}")
        return False

if __name__ == "__main__":
    # Obtenir le token
    token = get_jwt_token()
    
    if token:
        # Tester le token
        test_token(token)