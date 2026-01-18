import httpx
import logging
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from urllib.parse import urlencode
from app.core.config import settings
import json

logger = logging.getLogger(__name__)

class FacebookAuthService:
    """
    Service d'authentification Facebook pour Live Commerce
    Version PRODUCTION corrigée et robuste
    """
    
    def __init__(self):
        # Configuration avec validation
        self.app_id = settings.FACEBOOK_APP_ID or ""
        self.app_secret = settings.FACEBOOK_APP_SECRET or ""
        self.redirect_uri = settings.FACEBOOK_APP_REDIRECT_URI or ""
        self.api_version = getattr(settings, 'FACEBOOK_API_VERSION', 'v18.0')
        
        # 🔥 VALIDATION CRITIQUE
        if not self.app_id or not self.app_secret or not self.redirect_uri:
            logger.error("❌ Configuration Facebook incomplète")
            # On continue quand même mais en mode dégradé
        
        self.base_url = f"https://graph.facebook.com/{self.api_version}"
        logger.info(f"✅ FacebookAuthService initialisé")
        
        # Client HTTP réutilisable avec meilleurs timeouts
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
            headers={
                'User-Agent': 'LiveCommerceApp/1.0',
                'Accept': 'application/json',
            }
        )
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()
    
    def get_oauth_url(self, state: str = None) -> str:
        """
        🔥 CORRIGÉ: Génère l'URL OAuth 2.0 optimisée
        """
        # SCOPES ESSENTIELS
        essential_scopes = [
            "email",
            "public_profile",
            "pages_show_list",
            "pages_read_engagement",
            "pages_manage_posts",
            "pages_manage_engagement",
            "pages_messaging",
            "business_management",
        ]
        
        params = {
            "client_id": self.app_id,
            "redirect_uri": self.redirect_uri,
            "scope": ",".join(essential_scopes),
            "response_type": "code",
            "auth_type": "rerequest",
        }
        
        if state:
            params["state"] = str(state)
        
        base_auth_url = f"https://www.facebook.com/{self.api_version}/dialog/oauth"
        oauth_url = f"{base_auth_url}?{urlencode(params)}"
        
        logger.info(f"🔗 URL OAuth générée")
        return oauth_url
    
    async def exchange_code_for_token(self, code: str) -> Dict[str, Any]:
        """
        🔥 CORRIGÉ: Échange le code contre un token d'accès
        """
        if not code or code.strip() == "":
            raise ValueError("Code d'autorisation vide ou invalide")
        
        logger.info(f"🔄 Échange code contre token")
        
        try:
            # Étape 1: Token court terme
            token_url = f"{self.base_url}/oauth/access_token"
            params = {
                "client_id": self.app_id,
                "client_secret": self.app_secret,
                "redirect_uri": self.redirect_uri,
                "code": code.strip(),
            }
            
            logger.debug(f"📤 Requête token: {token_url}")
            response = await self.client.get(token_url, params=params)
            
            if response.status_code != 200:
                error_data = self._parse_facebook_error(response)
                error_msg = error_data.get("message", "Erreur inconnue")
                logger.error(f"❌ Facebook OAuth error: {error_msg}")
                raise Exception(f"Erreur Facebook OAuth: {error_msg}")
            
            token_data = response.json()
            access_token = token_data.get("access_token")
            
            if not access_token:
                raise Exception("Facebook n'a pas retourné de token d'accès")
            
            logger.info(f"✅ Token obtenu")
            
            # Étape 2: Essayer le token long-lived
            try:
                long_token_data = await self._get_long_lived_token(access_token)
                token_data.update(long_token_data)
                logger.info("✅ Token long-lived obtenu")
            except Exception as e:
                logger.warning(f"⚠️ Token long-lived échoué: {e}")
                # On garde le token court
                token_data["token_type"] = "short"
            
            # Ajouter l'expiration
            expires_in = token_data.get("expires_in", 7200)
            expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
            token_data["expires_at"] = expires_at.isoformat()
            
            return token_data
            
        except httpx.TimeoutException:
            logger.error("⏱️ Timeout Facebook OAuth")
            raise Exception("Timeout lors de la connexion à Facebook")
        except httpx.RequestError as e:
            logger.error(f"🌐 Erreur réseau: {e}")
            # 🔥 CORRECTION: Meilleur message d'erreur réseau
            raise Exception(f"Erreur réseau: Impossible de se connecter à Facebook. Vérifiez votre connexion internet.")
        except Exception as e:
            logger.error(f"💥 Erreur inattendue: {e}")
            raise
    
    async def _get_long_lived_token(self, short_lived_token: str) -> Dict[str, Any]:
        """
        🔥 CORRIGÉ: Obtient un token long-lived
        """
        token_url = f"{self.base_url}/oauth/access_token"
        params = {
            "grant_type": "fb_exchange_token",
            "client_id": self.app_id,
            "client_secret": self.app_secret,
            "fb_exchange_token": short_lived_token,
        }
        
        response = await self.client.get(token_url, params=params)
        
        if response.status_code != 200:
            error_data = self._parse_facebook_error(response)
            raise Exception(f"Long-lived token failed: {error_data.get('message')}")
        
        token_data = response.json()
        token_data["token_type"] = "long"
        return token_data
    
    async def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """
        🔥 CORRIGÉ: Récupère les infos utilisateur
        """
        user_url = f"{self.base_url}/me"
        params = {
            "fields": "id,name,first_name,last_name,email,picture{url}",
            "access_token": access_token,
        }
        
        try:
            logger.debug(f"📥 Récupération infos utilisateur...")
            response = await self.client.get(user_url, params=params)
            
            if response.status_code != 200:
                error_data = self._parse_facebook_error(response)
                raise Exception(f"Facebook API Error: {error_data.get('message')}")
            
            user_data = response.json()
            
            formatted_data = {
                "id": user_data.get("id", ""),
                "name": user_data.get("name", ""),
                "first_name": user_data.get("first_name", ""),
                "last_name": user_data.get("last_name", ""),
                "email": user_data.get("email", ""),
            }
            
            if "picture" in user_data and "data" in user_data["picture"]:
                formatted_data["profile_pic_url"] = user_data["picture"]["data"].get("url", "")
            
            logger.info(f"👤 Utilisateur récupéré: {formatted_data.get('name')}")
            return formatted_data
            
        except httpx.RequestError as e:
            # 🔥 CORRECTION: Meilleure gestion des erreurs réseau
            logger.error(f"❌ Erreur réseau récupération utilisateur: {e}")
            raise Exception(f"Erreur réseau: Impossible de récupérer les infos utilisateur. Code erreur: {getattr(e, 'errno', 'N/A')}")
        except Exception as e:
            logger.error(f"❌ Erreur récupération utilisateur: {e}")
            raise
    
    async def get_user_pages(self, user_access_token: str) -> List[Dict[str, Any]]:
        """
        🔥 CORRIGÉ: Récupère les pages Facebook SANS le champ 'perms' obsolète
        """
        pages_url = f"{self.base_url}/me/accounts"
        
        # 🔥 CORRECTION: Retirer 'perms' qui n'existe plus
        # Utiliser 'tasks' à la place pour les permissions
        params = {
            "access_token": user_access_token,
            "fields": "id,name,category,fan_count,about,access_token,picture{url},cover{source},tasks",
            "limit": 100,
        }
        
        try:
            logger.info("📄 Récupération pages Facebook...")
            response = await self.client.get(pages_url, params=params)
            
            if response.status_code != 200:
                error_data = self._parse_facebook_error(response)
                error_msg = error_data.get("message", "Erreur inconnue")
                
                # Gérer les erreurs de permission
                if "permission" in error_msg.lower() or "OAuthException" in error_msg:
                    logger.error(f"🔒 Permission insuffisante: {error_msg}")
                    raise Exception("Permissions Facebook insuffisantes. Veuillez réautoriser l'application avec toutes les permissions nécessaires.")
                
                logger.error(f"❌ Erreur API Facebook: {error_msg}")
                raise Exception(f"Erreur Facebook API: {error_msg}")
            
            result = response.json()
            pages_data = result.get("data", [])
            
            formatted_pages = []
            for page in pages_data:
                formatted_page = self._format_page_data(page)
                formatted_pages.append(formatted_page)
            
            logger.info(f"✅ {len(formatted_pages)} pages récupérées")
            return formatted_pages
            
        except httpx.RequestError as e:
            # 🔥 CORRECTION: Meilleure gestion des erreurs réseau
            logger.error(f"🌐 Erreur réseau récupération pages: {e}")
            raise Exception(f"Erreur réseau lors de la récupération des pages. Vérifiez votre connexion internet.")
        except Exception as e:
            logger.error(f"❌ Erreur récupération pages: {e}")
            raise
    
    def _format_page_data(self, page_data: Dict) -> Dict[str, Any]:
        """
        🔥 CORRIGÉ: Formate les données de page SANS 'perms'
        """
        formatted = {
            "id": page_data.get("id", ""),
            "name": page_data.get("name", "Page sans nom"),
            "category": page_data.get("category"),
            "fan_count": page_data.get("fan_count", 0),
            "about": page_data.get("about"),
            "access_token": page_data.get("access_token", ""),
            "is_selected": False,
        }
        
        # Photo de profil
        if "picture" in page_data and "data" in page_data["picture"]:
            formatted["profile_pic_url"] = page_data["picture"]["data"].get("url")
        
        # Photo de couverture
        if "cover" in page_data:
            formatted["cover_photo_url"] = page_data["cover"].get("source")
        
        # 🔥 CORRECTION: Utiliser 'tasks' au lieu de 'perms'
        tasks = page_data.get("tasks", [])
        formatted["tasks"] = tasks
        
        # Déterminer les permissions basées sur les tasks
        formatted["is_admin"] = "ADMINISTER" in tasks or "MANAGE" in tasks
        formatted["can_create_content"] = "CREATE_CONTENT" in tasks
        formatted["can_moderate"] = "MODERATE_CONTENT" in tasks
        
        return formatted
    
    def _parse_facebook_error(self, response: httpx.Response) -> Dict[str, Any]:
        """
        🔥 CORRIGÉ: Parse les erreurs Facebook
        """
        try:
            if response.content:
                content = response.json()
                error_data = content.get("error", {})
                logger.error(f"📛 Facebook API Error: {json.dumps(error_data, indent=2)}")
                return error_data
        except Exception as e:
            logger.error(f"❌ Erreur parsing erreur Facebook: {e}")
        
        return {
            "message": f"HTTP {response.status_code}: {response.text[:200]}",
            "code": response.status_code
        }
    
    def calculate_token_expiry(self, expires_in: int) -> datetime:
        """
        🔥 CORRIGÉ: Calcule la date d'expiration
        """
        return datetime.utcnow() + timedelta(seconds=expires_in)
    
    async def test_connection(self) -> bool:
        """
        🔥 NOUVEAU: Teste la connexion à l'API Facebook
        """
        test_url = "https://graph.facebook.com"
        try:
            response = await self.client.get(test_url, timeout=10.0)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"❌ Test connexion Facebook échoué: {e}")
            return False
    
    async def close(self):
        """
        Fermer le client HTTP
        """
        await self.client.aclose()


# 🔥 Instance avec meilleure gestion d'erreur
try:
    facebook_auth_service = FacebookAuthService()
    logger.info("🚀 FacebookAuthService initialisé avec succès")
except Exception as e:
    logger.critical(f"💥 ÉCHEC initialisation FacebookAuthService: {e}")
    
    # Service en mode dégradé
    class DegradedFacebookAuthService:
        def __init__(self):
            self.app_id = "NOT_CONFIGURED"
            logger.error("⚠️ Service Facebook en mode dégradé")
        
        def get_oauth_url(self, state=None):
            raise Exception("Service Facebook non configuré. Vérifiez les variables d'environnement.")
        
        async def exchange_code_for_token(self, code):
            raise Exception("Service Facebook non configuré. Vérifiez les variables d'environnement.")
        
        async def get_user_info(self, access_token):
            raise Exception("Service Facebook non configuré.")
        
        async def get_user_pages(self, user_access_token):
            raise Exception("Service Facebook non configuré.")
    
    facebook_auth_service = DegradedFacebookAuthService()