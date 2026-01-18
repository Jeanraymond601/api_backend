import requests
import json
import time
import os
from datetime import datetime, timedelta

# Configuration
BASE_URL = "https://3d1a525dacf6.ngrok-free.app"
CREDENTIALS = {
    "email": "teamsora40@gmail.com",
    "password": "Team@123"
}

# Fichier pour stocker le token
TOKEN_FILE = "facebook_token.json"

def login_and_get_token():
    """Se connecte et récupère un token"""
    print("🔑 Connexion au système...")
    
    try:
        response = requests.post(
            f"{BASE_URL}/auth/login",
            json=CREDENTIALS,
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token")
            
            if token:
                # Sauvegarde le token avec timestamp
                token_data = {
                    "token": token,
                    "expires_at": (datetime.now() + timedelta(hours=6)).isoformat(),
                    "seller_id": data.get("seller_id"),
                    "user_name": data.get("full_name")
                }
                
                with open(TOKEN_FILE, 'w') as f:
                    json.dump(token_data, f)
                
                print(f"✅ Connecté: {data.get('full_name')}")
                print(f"📅 Token valide jusqu'à: {token_data['expires_at']}")
                return token
        else:
            print(f"❌ Erreur connexion: {response.text}")
            
    except Exception as e:
        print(f"❌ Erreur réseau: {e}")
    
    return None

def get_valid_token():
    """Récupère un token valide (nouveau ou depuis fichier)"""
    # Vérifie si un token existe déjà
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, 'r') as f:
                token_data = json.load(f)
            
            # Vérifie si le token n'est pas expiré
            expires_at = datetime.fromisoformat(token_data.get("expires_at", "2000-01-01"))
            if datetime.now() < expires_at:
                print(f"🔄 Token existant chargé ({token_data.get('user_name')})")
                return token_data["token"]
            else:
                print("🔄 Token expiré, reconnexion...")
                
        except:
            print("🔄 Fichier token invalide, reconnexion...")
    
    # Sinon, se connecte
    return login_and_get_token()

class FacebookAutoSystem:
    def __init__(self):
        self.token = get_valid_token()
        self.headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        self.base_url = BASE_URL
        
    def make_request(self, method, endpoint, **kwargs):
        """Fait une requête HTTP avec gestion d'erreurs"""
        if not self.token:
            print("❌ Pas de token disponible")
            return None
        
        url = f"{self.base_url}{endpoint}"
        
        try:
            response = requests.request(
                method, url, 
                headers=self.headers, 
                timeout=30,
                **kwargs
            )
            
            # Si token expiré, essaie de se reconnecter
            if response.status_code in [401, 403]:
                print("🔄 Token expiré, tentative de reconnexion...")
                self.token = login_and_get_token()
                if self.token:
                    self.headers = {"Authorization": f"Bearer {self.token}"}
                    # Réessaie la requête
                    return self.make_request(method, endpoint, **kwargs)
                else:
                    print("❌ Impossible de se reconnecter")
                    return None
            
            # Pour debug
            if response.status_code >= 400:
                print(f"⚠️  Erreur {response.status_code} pour {endpoint}")
                print(f"   Message: {response.text[:200]}")
            
            response.raise_for_status()
            
            # Si succès
            if response.status_code in [200, 201]:
                try:
                    return response.json()
                except:
                    return {"success": True, "raw": response.text}
            else:
                return response.json()
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Erreur requête {method} {endpoint}: {e}")
            return None
    
    def check_facebook_status(self):
        """Vérifie l'état du système Facebook"""
        print("\n" + "="*60)
        print("📊 ÉTAT DU SYSTÈME FACEBOOK")
        print("="*60)
        
        # 1. Statut auto-reply
        print("\n1. 🔧 Auto-reply:")
        response = self.make_request("GET", "/api/v1/facebook/auto-reply/status")
        if response and response.get("success"):
            print(f"   ✅ Page: {response.get('page_name')}")
            print(f"   ✅ Statut: {'ACTIF' if response.get('enabled') else 'INACTIF'}")
            print(f"   ✅ Template: {response.get('template_preview', 'Par défaut')}")
        
        # 2. Webhooks
        print("\n2. 🌐 Webhooks:")
        response = self.make_request("GET", "/api/v1/facebook/webhook/health")
        if response and response.get("success"):
            subs = response.get('subscriptions', {})
            print(f"   ✅ Activés: {subs.get('count', 0)}")
            for sub in subs.get('active', []):
                print(f"   📍 {sub.get('page_name')} - Dernier: {sub.get('last_received', 'Jamais')}")
        
        # 3. Synchronisation
        print("\n3. 🔄 Synchronisation:")
        print("   Lancement sync des posts...")
        response = self.make_request("POST", "/api/v1/facebook/sync/posts", 
                                    params={"limit": 10, "since_days": 1})
        if response:
            print(f"   ✅ {response.get('message', 'Terminé')}")
            print(f"   📊 {response.get('posts_synced', 0)} posts, {response.get('comments_synced', 0)} commentaires")
        
        time.sleep(2)
        
        # 4. Commentaires en attente
        print("\n4. 📋 Commentaires:")
        response = self.make_request("GET", "/api/v1/facebook/comments/pending")
        if response and response.get("success"):
            count = response.get("count", 0)
            print(f"   ⏳ En attente: {count}")
            if count > 0:
                for comment in response.get("comments", [])[:3]:
                    print(f"   👤 {comment.get('user_name')}: {comment.get('message', '')[:50]}...")
        
        # 5. Commandes prêtes
        print("\n5. 🛒 Commandes prêtes:")
        response = self.make_request("GET", "/api/v1/facebook/comments/ready-for-orders")
        if response and response.get("success"):
            count = response.get("count", 0)
            print(f"   ✅ Prêtes: {count}")
            if count > 0:
                for comment in response.get("comments", [])[:3]:
                    print(f"   🎯 {comment.get('user_name')}: {comment.get('detected_code_article', 'N/A')}")
        
        print("\n" + "="*60)
    
    def process_new_comments(self):
        """Traite les nouveaux commentaires"""
        print("\n" + "="*60)
        print("🤖 TRAITEMENT DES COMMENTAIRES")
        print("="*60)
        
        # 1. Active l'auto-reply
        print("\n1. Activation auto-reply...")
        response = self.make_request("POST", "/api/v1/facebook/auto-reply/enable", 
                                    json={"enabled": True, "template_name": "simple_confirmation"})
        if response and response.get("success"):
            print(f"   ✅ {response.get('message')}")
        
        # 2. Traite les commentaires avec NLP
        print("\n2. Traitement NLP...")
        response = self.make_request("POST", "/api/v1/facebook/comments/process", 
                                    params={"auto_create_orders": True})
        if response and response.get("success"):
            processed = response.get("processed", 0)
            orders = response.get("orders_created", 0)
            print(f"   ✅ {processed} commentaire(s) traité(s)")
            if orders > 0:
                print(f"   🛒 {orders} commande(s) créée(s)")
        
        # 3. Récupère les vrais commentaires Facebook
        print("\n3. Recherche commentaires Facebook...")
        response = self.make_request("GET", "/api/v1/facebook/comments/ready-for-orders")
        
        if not response or not response.get("success"):
            print("   📭 Aucun commentaire trouvé")
            return
        
        comments = response.get("comments", [])
        
        # Filtre les vrais commentaires Facebook (IDs avec underscore)
        real_comments = []
        for comment in comments:
            comment_id = comment.get("id", "")
            if "_" in comment_id and len(comment_id) > 15 and not comment_id.startswith("fb"):
                real_comments.append(comment)
        
        print(f"   ✅ {len(real_comments)} vrai(s) commentaire(s) Facebook")
        
        if not real_comments:
            return
        
        # 4. Traite les vrais commentaires
        print("\n4. Traitement des commentaires Facebook:")
        success_count = 0
        
        for i, comment in enumerate(real_comments[:5]):  # 5 maximum
            comment_id = comment["id"]
            user_name = comment["user_name"]
            product = comment.get("detected_code_article", "produit")
            message = comment.get("message", "")[:50] + "..." if len(comment.get("message", "")) > 50 else comment.get("message", "")
            
            print(f"\n   {i+1}. 👤 {user_name}")
            print(f"      📦 Produit: {product}")
            print(f"      💬 Message: {message}")
            
            # Crée la commande
            print(f"      📝 Création commande...")
            order_response = self.make_request("POST", f"/api/v1/facebook/comments/{comment_id}/create-order")
            
            if order_response and order_response.get("success"):
                order_num = order_response.get("order_number", "N/A")
                print(f"      ✅ Commande: {order_num}")
            else:
                print(f"      ⚠️  Commande existe déjà ou erreur")
            
            time.sleep(1)
            
            # Envoie la réponse auto
            print(f"      🤖 Envoi réponse auto...")
            reply_response = self.make_request("POST", f"/api/v1/facebook/auto-reply/{comment_id}/reply")
            
            if reply_response and reply_response.get("success"):
                fb_id = reply_response.get("facebook_response_id", "N/A")
                print(f"      ✅ Réponse envoyée! ID: {fb_id}")
                success_count += 1
            else:
                print(f"      ❌ Erreur réponse")
            
            # Pause pour éviter rate limiting
            if i < len(real_comments[:5]) - 1:
                print(f"      ⏳ Pause 3 secondes...")
                time.sleep(3)
        
        print("\n" + "="*60)
        print(f"📊 RÉSULTATS: {success_count}/{len(real_comments[:5])} réponses envoyées")
        print("="*60)
    
    def test_with_new_comment(self, comment_text="JP VET-SW01 svp"):
        """Teste avec un commentaire simulé"""
        print("\n" + "="*60)
        print("🧪 TEST AVEC NOUVEAU COMMENTAIRE")
        print("="*60)
        
        print(f"Commentaire test: '{comment_text}'")
        
        # 1. Traitement NLP du message
        print("\n1. Analyse NLP...")
        response = self.make_request("GET", f"/api/v1/facebook/comments/test-intent?text={comment_text}")
        if response and response.get("success"):
            print(f"   ✅ Intention: {response.get('intent')}")
            print(f"   ✅ Confiance: {response.get('confidence')}")
            print(f"   ✅ Produits: {response.get('product_codes')}")
        
        # 2. Génération réponse test
        print("\n2. Génération réponse test...")
        response = self.make_request("POST", "/api/v1/facebook/auto-reply/test-message",
                                   json={
                                       "comment_text": comment_text,
                                       "customer_name": "Client Test",
                                       "order_number": "SHO-TEST-001",
                                       "total_amount": 39.99
                                   })
        if response and response.get("success"):
            print(f"   ✅ Message généré ({response.get('message_length', 0)} caractères)")
            print(f"   📝 Preview: {response.get('generated_message', '')[:100]}...")
        
        print("\n" + "="*60)
        print("💡 POUR TESTER EN VRAI:")
        print("1. Poste un commentaire 'JP VET-SW01' sur ta page Facebook")
        print("2. Lance ce script pour traiter")
        print("3. Vérifie que la réponse est postée sur Facebook")
        print("="*60)
    
    def continuous_monitor(self, interval_minutes=5):
        """Surveillance continue"""
        print("\n" + "="*60)
        print(f"🔄 SURVEILLANCE CONTINUE (toutes les {interval_minutes} min)")
        print("="*60)
        
        cycle = 0
        try:
            while True:
                cycle += 1
                current_time = datetime.now().strftime("%H:%M:%S")
                print(f"\n🔄 CYCLE #{cycle} - {current_time}")
                
                # Vérifie l'état
                self.check_facebook_status()
                
                # Traite les commentaires
                self.process_new_comments()
                
                print(f"\n⏳ Prochain cycle dans {interval_minutes} minutes...")
                time.sleep(interval_minutes * 60)
                
        except KeyboardInterrupt:
            print("\n\n🛑 Surveillance arrêtée")
    
    def run_interactive(self):
        """Mode interactif"""
        print("\n" + "="*60)
        print("🤖 SYSTÈME AUTO-FACEBOOK - MODE INTERACTIF")
        print("="*60)
        print("1. Vérifier l'état du système")
        print("2. Traiter les commentaires")
        print("3. Tester avec un nouveau commentaire")
        print("4. Surveillance continue")
        print("5. Quitter")
        print("="*60)
        
        while True:
            try:
                choice = input("\n👉 Choisis une option (1-5): ").strip()
                
                if choice == "1":
                    self.check_facebook_status()
                elif choice == "2":
                    self.process_new_comments()
                elif choice == "3":
                    comment = input("Entre un commentaire test (ex: JP VET-SW01): ").strip()
                    self.test_with_new_comment(comment or "JP VET-SW01 svp")
                elif choice == "4":
                    interval = input("Intervalle en minutes (défaut: 5): ").strip()
                    try:
                        interval = int(interval) if interval else 5
                        self.continuous_monitor(interval)
                    except ValueError:
                        print("⚠️  Intervalle invalide, utilisation de 5 minutes")
                        self.continuous_monitor(5)
                elif choice == "5":
                    print("👋 Au revoir!")
                    break
                else:
                    print("❌ Option invalide")
                    
            except KeyboardInterrupt:
                print("\n\n👋 Au revoir!")
                break
            except Exception as e:
                print(f"❌ Erreur: {e}")

def main():
    """Fonction principale"""
    print("\n" + "="*60)
    print("🤖 AUTO-FACEBOOK SYSTEM v1.0")
    print("="*60)
    
    # Initialise le système
    system = FacebookAutoSystem()
    
    if not system.token:
        print("❌ Impossible de se connecter. Vérifie tes credentials.")
        return
    
    # Mode interactif
    system.run_interactive()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ Erreur fatale: {e}")
        import traceback
        traceback.print_exc()