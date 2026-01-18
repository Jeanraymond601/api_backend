#!/usr/bin/env python3
"""
AUTO-SYNC-AND-REPLY FIXED - Version sans émojis pour Windows
"""

import requests
import json
import time
import sys
from datetime import datetime
import logging

# Configuration
BASE_URL = "https://3d1a525dacf6.ngrok-free.app"
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiZmMxMjZhODItNDFjNi00ZjQ4LWE1MGMtYzEzZTBiM2M4YjE5IiwiZW1haWwiOiJ0ZWFtc29yYTQwQGdtYWlsLmNvbSIsInJvbGUiOiJWRU5ERVVSIiwiZnVsbF9uYW1lIjoiSmVhbiBSYXltb25kIiwiZXhwIjoxNzY4NjM4MTQ0LCJpYXQiOjE3Njg2MzQ1NDQsIm5iZiI6MTc2ODYzNDU0NCwic2VsbGVyX2lkIjoiNTNlZTBiNzEtZGM1Mi00NDhjLWIyNjUtZTRiNzc2ZGJiYWIyIn0.-DSxCMacuKAvcGA8UFif_9HSOEei73TLzRocKJHK2sE"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

# Setup logging SANS émojis
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('auto_sync.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def make_request(method, endpoint, **kwargs):
    """Fait une requête HTTP avec gestion d'erreurs"""
    url = f"{BASE_URL}{endpoint}"
    
    try:
        response = requests.request(method, url, headers=headers, **kwargs, timeout=30)
        
        if response.status_code in [401, 403]:
            logger.error("Token expire! Regenerer un nouveau token.")
            return None
        
        # Pour debug: affiche l'erreur 500
        if response.status_code == 500:
            logger.error(f"Erreur 500 pour {endpoint}: {response.text[:200]}")
        
        response.raise_for_status()
        return response.json()
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Erreur requete {method} {endpoint}: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Erreur JSON pour {endpoint}: {e}")
        return None

def check_token():
    """Verifie si le token est valide"""
    logger.info("Verification token...")
    response = make_request("GET", "/api/v1/facebook/auto-reply/status")
    
    if response and response.get("success"):
        logger.info(f"OK Token valide - Page: {response.get('page_name')}")
        return True
    else:
        logger.error("ERREUR Token invalide ou expire")
        return False

def enable_auto_reply():
    """Active l'auto-reply"""
    logger.info("Activation auto-reply...")
    
    data = {
        "enabled": True,
        "template_name": "simple_confirmation"
    }
    
    response = make_request("POST", "/api/v1/facebook/auto-reply/enable", json=data)
    
    if response and response.get("success"):
        logger.info(f"OK Auto-reply active: {response.get('message')}")
        return True
    else:
        logger.warning("ATTENTION Auto-reply non active")
        return False

def sync_posts():
    """Synchronise les posts Facebook"""
    logger.info("Synchronisation des posts...")
    
    params = {"limit": 5, "since_days": 7}  # 7 jours au lieu de 1
    response = make_request("POST", "/api/v1/facebook/sync/posts", params=params)
    
    if response and response.get("success"):
        posts = response.get("posts_synced", 0)
        comments = response.get("comments_synced", 0)
        logger.info(f"OK {posts} posts, {comments} commentaires synchronises")
        return posts, comments
    else:
        logger.warning("ATTENTION Pas de posts synchronises")
        return 0, 0

def get_pending_comments():
    """Recupere les commentaires en attente"""
    logger.info("Recherche commentaires en attente...")
    
    response = make_request("GET", "/api/v1/facebook/comments/pending")
    
    if response and response.get("success"):
        count = response.get("count", 0)
        total = response.get("total", 0)
        
        if count > 0:
            logger.info(f"TROUVE {count} commentaire(s) en attente (total: {total})")
            return response.get("comments", [])
        else:
            logger.info("AUCUN commentaire en attente")
            return []
    else:
        logger.warning("ERREUR recuperation commentaires")
        return []

def process_comments(auto_create_orders=True):
    """Traite les commentaires avec NLP"""
    logger.info("Traitement NLP des commentaires...")
    
    params = {"auto_create_orders": auto_create_orders}
    response = make_request("POST", "/api/v1/facebook/comments/process", params=params)
    
    if response and response.get("success"):
        processed = response.get("processed", 0)
        orders = response.get("orders_created", 0)
        
        if processed > 0:
            logger.info(f"OK {processed} commentaire(s) traite(s)")
            if orders > 0:
                logger.info(f"COMMANDE {orders} commande(s) creee(s)")
        else:
            logger.info("INFO Aucun commentaire a traiter")
        
        return processed, orders
    else:
        logger.warning("ERREUR traitement commentaires")
        return 0, 0

def get_ready_orders():
    """Recupere les commentaires prets pour commandes"""
    logger.info("Recherche commandes a creer...")
    
    response = make_request("GET", "/api/v1/facebook/comments/ready-for-orders")
    
    if response and response.get("success"):
        count = response.get("count", 0)
        
        if count > 0:
            logger.info(f"PRET {count} commentaire(s) pret(s) pour commandes")
            return response.get("comments", [])
        else:
            logger.info("AUCUNE commande prete")
            return []
    else:
        logger.warning("ERREUR recuperation commandes")
        return []

def send_auto_reply(comment_id, comment_info=None):
    """Envoie une reponse automatique"""
    if comment_info:
        user = comment_info.get("user_name", "Client")
        product = comment_info.get("detected_code_article", "produit")
        logger.info(f"ENVOI auto-reply a {user} pour {product}...")
    else:
        logger.info(f"ENVOI auto-reply pour commentaire {comment_id}...")
    
    response = make_request("POST", f"/api/v1/facebook/auto-reply/{comment_id}/reply")
    
    if response and response.get("success"):
        order = response.get("order_number", "N/A")
        logger.info(f"OK Reponse envoyee! Commande: {order}")
        return True
    else:
        logger.warning(f"ECHEC reponse pour {comment_id}")
        return False

def create_order_for_comment(comment_id):
    """Cree une commande manuellement pour un commentaire"""
    logger.info(f"CREATION commande pour {comment_id}...")
    
    response = make_request("POST", f"/api/v1/facebook/comments/{comment_id}/create-order")
    
    if response and response.get("success"):
        order = response.get("order_number", "N/A")
        logger.info(f"OK Commande creee: {order}")
        return True
    else:
        logger.warning(f"ECHEC creation commande pour {comment_id}")
        return False

def smart_sync():
    """Synchronisation intelligente - seulement les commentaires avec produits valides"""
    logger.info("\n" + "="*60)
    logger.info("DEBUT SYNCHRONISATION INTELLIGENTE")
    logger.info("="*60)
    
    start_time = datetime.now()
    
    # 1. Verifie token
    if not check_token():
        return False
    
    # 2. Active auto-reply
    enable_auto_reply()
    
    # 3. Synchronise posts
    posts_synced, comments_synced = sync_posts()
    time.sleep(2)
    
    # 4. Traite les commentaires
    processed, orders_created = process_comments(auto_create_orders=True)
    
    # 5. Récupère seulement les commentaires avec vrais produits
    logger.info("Filtrage des commentaires valides...")
    ready_comments = get_ready_orders()
    
    # Filtre : seulement ceux avec codes produits valides
    valid_comments = []
    for comment in ready_comments:
        product_code = comment.get("detected_code_article", "")
        # Exclut les faux codes comme "0013 creee !"
        if product_code and len(product_code) > 3 and "-" in product_code:
            valid_comments.append(comment)
    
    logger.info(f"OK {len(valid_comments)} commentaire(s) valide(s) trouves")
    
    # 6. Traite les commentaires valides seulement
    auto_replies_sent = 0
    for comment in valid_comments[:3]:  # 3 maximum par cycle
        comment_id = comment.get("id")
        product_code = comment.get("detected_code_article", "")
        user_name = comment.get("user_name", "Client")
        
        if comment_id:
            logger.info(f"Traitement: {user_name} - {product_code}")
            
            # Essaye de créer une commande
            if orders_created == 0:
                if not create_order_for_comment(comment_id):
                    logger.info(f"Passe au suivant...")
                    continue
            
            # Envoie la reponse
            if send_auto_reply(comment_id, comment):
                auto_replies_sent += 1
            
            time.sleep(2)  # Evite le rate limiting
    
    # 7. Statistiques
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    logger.info("\n" + "="*60)
    logger.info("RESUME DU CYCLE")
    logger.info("="*60)
    logger.info(f"DUREE: {duration:.1f} secondes")
    logger.info(f"POSTS: {posts_synced}")
    logger.info(f"COMMENTAIRES: {comments_synced}")
    logger.info(f"TRAITES: {processed}")
    logger.info(f"COMMANDES: {orders_created}")
    logger.info(f"REPONSES: {auto_replies_sent}")
    logger.info("="*60)
    
    return True

def test_specific_comment(comment_id):
    """Teste un commentaire specifique"""
    logger.info(f"\nTEST COMMENTAIRE: {comment_id}")
    
    # 1. Creer la commande
    create_order_for_comment(comment_id)
    
    # 2. Envoyer la reponse
    send_auto_reply(comment_id)

if __name__ == "__main__":
    print("\n" + "="*60)
    print("AUTO-SYNC-AND-REPLY FIXED")
    print("="*60)
    print(f"URL: {BASE_URL}")
    print("="*60)
    
    try:
        # Teste d'abord un commentaire valide
        # Commentaires avec vrais produits:
        # - "122109774315164336_2610724639306294" (LIV-RM01)
        # - "fb021" (INF-CL01, INF-MS01)
        # - "fb006" (APL-AP2)
        
        logger.info("\nTEST AVEC COMMENTAIRE VALIDE...")
        test_specific_comment("122109774315164336_2610724639306294")
        
        time.sleep(3)
        
        # Puis synchro complete
        logger.info("\nLANCEMENT SYNCHRO COMPLETE...")
        smart_sync()
        
        print("\nOK Operation terminee avec succes!")
        
    except KeyboardInterrupt:
        print("\n\nARRETE - Au revoir!")
    except Exception as e:
        print(f"\nERREUR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)