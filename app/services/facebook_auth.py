# app/services/facebook_auth.py
import httpx
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)


class FacebookAuthService:
    def __init__(self):
        self.app_id = settings.FACEBOOK_APP_ID
        self.app_secret = settings.FACEBOOK_APP_SECRET
        self.redirect_uri = settings.FACEBOOK_REDIRECT_URI
        self.api_version = settings.FACEBOOK_API_VERSION
        self.base_url = f"https://graph.facebook.com/{self.api_version}"

    def get_oauth_url(self, state: str = None) -> str:
        """
        Version simplifiée avec permissions ESSENTIELLES seulement
        """
        # SCOPES MINIMAUX pour fonctionner
        essential_scopes: List[str] = [
            "email",                 # Requis  
            "pages_show_list",       # ⭐ NÉCESSAIRE pour voir les pages
            "pages_read_engagement", # ⭐ NÉCESSAIRE pour lire contenu
            "business_management",   # ⭐ NÉCESSAIRE pour Business API
            # ⭐⭐⭐ AJOUTE CES LIGNES CRITIQUES CI-DESSOUS ⭐⭐⭐
            "pages_manage_posts",    # PERMET DE PUBLIER
            "pages_manage_engagement", # PERMET DE MODÉRER
            "pages_manage_metadata", # PERMET DE MODIFIER LA PAGE
            "pages_read_user_content", # PERMET DE LIRE LES MESSAGES
            # "pages_messaging"      # Optionnel : pour le chat
        ]
        
        scope_param = ",".join(essential_scopes)
        
        # Construction URL optimisée
        oauth_url = (
            f"https://www.facebook.com/{self.api_version}/dialog/oauth?"
            f"client_id={self.app_id}&"
            f"redirect_uri={self.redirect_uri}&"
            f"scope={scope_param}&"
            f"response_type=code&"
            f"auth_type=rerequest&"
            f"display=popup"
        )
        
        if state:
            oauth_url += f"&state={state}"
        
        print(f"🎯 URL OAuth simplifiée générée")
        print(f"   Scopes: {scope_param}")
        
        return oauth_url

    async def exchange_code_for_token(self, code: str) -> Dict:
        """
        Échange le code OAuth contre un token d'accès
        """
        token_url = f"{self.base_url}/oauth/access_token"
        
        params = {
            "client_id": self.app_id,
            "client_secret": self.app_secret,
            "redirect_uri": self.redirect_uri,
            "code": code
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(token_url, params=params)
            response.raise_for_status()
            token_data = response.json()
            
        return token_data

    async def get_long_lived_token(self, short_lived_token: str) -> Dict:
        """
        Échange le token court contre un token long terme
        """
        token_url = f"{self.base_url}/oauth/access_token"
        
        params = {
            "grant_type": "fb_exchange_token",
            "client_id": self.app_id,
            "client_secret": self.app_secret,
            "fb_exchange_token": short_lived_token
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(token_url, params=params)
            response.raise_for_status()
            token_data = response.json()
            
        return token_data

    async def get_user_info(self, access_token: str) -> Dict:
        """
        Récupère les informations de l'utilisateur Facebook
        """
        user_url = f"{self.base_url}/me"
        
        params = {
            "fields": "id,name,first_name,last_name,email,picture",
            "access_token": access_token
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(user_url, params=params)
            response.raise_for_status()
            user_data = response.json()
            
        return user_data

    async def get_user_pages(self, user_access_token: str) -> List[Dict]:
        """
        Récupère la liste des pages dont l'utilisateur est admin
        """
        pages_url = f"{self.base_url}/me/accounts"
        
        params = {
            "access_token": user_access_token,
            "fields": "id,name,category,category_list,picture,cover,fan_count,about,description,access_token"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(pages_url, params=params)
            response.raise_for_status()
            pages_data = response.json()
            
        return pages_data.get("data", [])

    async def get_page_access_token(self, page_id: str, user_access_token: str) -> Optional[str]:
        """
        Récupère le token d'accès spécifique à une page
        """
        page_token_url = f"{self.base_url}/{page_id}"
        
        params = {
            "fields": "access_token",
            "access_token": user_access_token
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(page_token_url, params=params)
            response.raise_for_status()
            page_data = response.json()
            
        return page_data.get("access_token")

    def calculate_token_expiry(self, expires_in: int) -> datetime:
        """
        Calcule la date d'expiration du token
        """
        return datetime.utcnow() + timedelta(seconds=expires_in)

    async def validate_token(self, access_token: str) -> Dict:
        """
        Valide un token d'accès Facebook
        """
        debug_url = f"{self.base_url}/debug_token"
        
        params = {
            "input_token": access_token,
            "access_token": f"{self.app_id}|{self.app_secret}"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(debug_url, params=params)
            response.raise_for_status()
            debug_data = response.json()
            
        return debug_data.get("data", {})

    async def refresh_page_token_if_needed(self, page_id: str, current_token: str) -> Optional[str]:
        """
        Rafraîchit le token d'une page si nécessaire
        """
        try:
            debug_info = await self.validate_token(current_token)
            
            if debug_info.get("is_valid") and not debug_info.get("is_expired"):
                return current_token
                
            # Si le token est expiré, on doit demander à l'utilisateur de se reconnecter
            return None
            
        except Exception as e:
            logger.error(f"Erreur lors de la validation du token: {e}")
            return None


# Instance singleton
facebook_auth_service = FacebookAuthService()