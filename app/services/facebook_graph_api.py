# app/services/facebook_graph_api.py
import httpx
import logging
import asyncio
import json
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

class FacebookGraphAPIService:
    """
    🔥 SERVICE COMPLET CORRIGÉ pour l'API Graph Facebook
    Version Production - Optimisé pour Live Commerce
    Avec gestion robuste des erreurs et retry automatique
    """
    
    def __init__(self, api_version: str = "v18.0", timeout: int = 30):
        self.base_url = f"https://graph.facebook.com/{api_version}"
        self.timeout = timeout
        self.client = None
        self.rate_limit_remaining = 100  # Estimation
        self.last_request_time = None
        
        logger.info(f"🚀 FacebookGraphAPIService initialisé (v{api_version})")
    
    async def _ensure_client(self):
        """Crée ou recrée le client HTTP si nécessaire"""
        if self.client is None or self.client.is_closed:
            transport = httpx.AsyncHTTPTransport(retries=3)
            self.client = httpx.AsyncClient(
                timeout=self.timeout,
                transport=transport,
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
            )
    
    async def close(self):
        """Ferme proprement le client"""
        if self.client and not self.client.is_closed:
            await self.client.aclose()
            self.client = None
    
    async def __aenter__(self):
        await self._ensure_client()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    # ==================== CORE REQUEST METHOD ====================
    
    async def _make_request(
        self, 
        method: str, 
        endpoint: str, 
        params: Dict = None, 
        data: Dict = None,
        headers: Dict = None,
        retries: int = 2,
        backoff_factor: float = 1.5
    ) -> Dict[str, Any]:
        """
        🔥 CORRIGÉ: Méthode de requête robuste avec retry exponentiel
        """
        await self._ensure_client()
        
        # Construire l'URL complète
        if endpoint.startswith(("http://", "https://")):
            url = endpoint
        else:
            url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        # Headers par défaut
        default_headers = {
            "User-Agent": "FacebookGraphAPI/1.0 (LiveCommerce)",
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate",
        }
        if headers:
            default_headers.update(headers)
        
        # Gestion du rate limiting
        await self._respect_rate_limit()
        
        last_exception = None
        
        for attempt in range(retries + 1):
            try:
                # Backoff exponentiel avant les retries
                if attempt > 0:
                    wait_time = backoff_factor ** attempt  # 1.5^1, 1.5^2, ...
                    logger.warning(f"🔄 Retry {attempt}/{retries} dans {wait_time:.1f}s")
                    await asyncio.sleep(wait_time)
                
                # Préparer les paramètres de la requête
                request_params = {}
                if params:
                    # Filtrer les paramètres None
                    request_params = {k: v for k, v in params.items() if v is not None}
                
                # Faire la requête
                logger.debug(f"📤 Facebook API: {method} {url} (attempt {attempt + 1})")
                
                if method.upper() == "GET":
                    response = await self.client.get(
                        url, 
                        params=request_params, 
                        headers=default_headers
                    )
                elif method.upper() == "POST":
                    response = await self.client.post(
                        url, 
                        params=request_params,
                        json=data if data else None,
                        headers=default_headers
                    )
                elif method.upper() == "DELETE":
                    response = await self.client.delete(
                        url, 
                        params=request_params,
                        headers=default_headers
                    )
                elif method.upper() == "PUT":
                    response = await self.client.put(
                        url,
                        params=request_params,
                        json=data if data else None,
                        headers=default_headers
                    )
                else:
                    raise ValueError(f"Méthode non supportée: {method}")
                
                # Mettre à jour le timestamp de la dernière requête
                self.last_request_time = datetime.utcnow()
                
                # Analyser la réponse
                logger.debug(f"📥 Response: {response.status_code}")
                
                # Gérer les erreurs HTTP
                if response.status_code >= 500:
                    error_msg = f"Erreur serveur Facebook: {response.status_code}"
                    logger.warning(f"⚠️ {error_msg}")
                    
                    if attempt < retries:
                        continue
                    else:
                        response.raise_for_status()
                
                # Pour les erreurs 4xx, on ne retry pas (sauf 429 - rate limit)
                if response.status_code in [429] and attempt < retries:
                    # Rate limit - attendre plus longtemps
                    await asyncio.sleep(5 * (attempt + 1))
                    continue
                
                response.raise_for_status()
                
                # Parser la réponse JSON
                if response.content:
                    result = response.json()
                    
                    # 🔥 VÉRIFIER LES ERREURS FACEBOOK DANS LA RÉPONSE
                    if "error" in result:
                        error_data = result["error"]
                        error_code = error_data.get("code")
                        error_msg = error_data.get("message", "Erreur Facebook inconnue")
                        error_type = error_data.get("type", "OAuthException")
                        
                        logger.error(f"📛 Facebook API Error [{error_code}]: {error_msg}")
                        
                        # Gestion spécifique par code d'erreur
                        if error_code in [190, 2500]:  # Token expiré/invalide
                            raise Exception(f"Token Facebook expiré ou invalide: {error_msg}")
                        elif error_code == 200:  # Permission manquante
                            raise Exception(f"Permission manquante: {error_msg}")
                        elif error_code == 100:  # Paramètre invalide
                            raise Exception(f"Paramètre API invalide: {error_msg}")
                        elif error_code == 4:  # Rate limit
                            if attempt < retries:
                                await asyncio.sleep(10)  # Longue attente pour rate limit
                                continue
                            raise Exception(f"Rate limit atteint: {error_msg}")
                        elif error_code == 10:  # IP non autorisée
                            raise Exception(f"IP non autorisée: {error_msg}")
                        elif error_code == 368:  # Temporary block
                            raise Exception(f"Compte temporairement bloqué: {error_msg}")
                        else:
                            raise Exception(f"Erreur Facebook [{error_code}]: {error_msg}")
                    
                    # Mettre à jour les infos de rate limit depuis les headers
                    await self._update_rate_limit_from_headers(response.headers)
                    
                    return result
                else:
                    # Réponse vide mais succès
                    return {"success": True, "id": url.split('/')[-1]}
                
            except httpx.HTTPStatusError as e:
                last_exception = e
                status_code = e.response.status_code if e.response else 0
                
                logger.error(f"❌ HTTP Error {status_code} on {method} {url}")
                
                # Ne pas retry pour les erreurs client (4xx) sauf 429
                if status_code < 500 and status_code != 429:
                    break
                    
                if attempt < retries:
                    continue
                else:
                    # Essayer de récupérer le message d'erreur
                    try:
                        error_data = e.response.json()
                        error_msg = error_data.get("error", {}).get("message", str(e))
                    except:
                        error_msg = str(e)
                    
                    raise Exception(f"Facebook API HTTP Error: {error_msg}")
                    
            except httpx.TimeoutException:
                last_exception = "Timeout"
                logger.error(f"⏱️ Timeout on {method} {url}")
                
                if attempt < retries:
                    continue
                raise Exception("Timeout Facebook API")
                
            except httpx.RequestError as e:
                last_exception = e
                logger.error(f"🌐 Network error: {e}")
                
                if attempt < retries:
                    continue
                raise Exception(f"Erreur réseau Facebook: {str(e)}")
                
            except Exception as e:
                last_exception = e
                logger.error(f"💥 Unexpected error: {e}", exc_info=True)
                
                if attempt < retries:
                    continue
                raise
        
        # Si on arrive ici, tous les retries ont échoué
        raise Exception(f"Toutes les tentatives ont échoué: {last_exception}")
    
    async def _respect_rate_limit(self):
        """Respecte les limites de rate de l'API Facebook"""
        if self.last_request_time:
            elapsed = (datetime.utcnow() - self.last_request_time).total_seconds()
            # Facebook recommande max 200 req/heure => ~1 req/18s
            if elapsed < 0.1:  # 100ms entre les requêtes minimum
                await asyncio.sleep(0.1 - elapsed)
        
        # Si on a peu de requêtes restantes, on ralentit
        if self.rate_limit_remaining < 10:
            await asyncio.sleep(1.0)
        elif self.rate_limit_remaining < 30:
            await asyncio.sleep(0.5)
    
    async def _update_rate_limit_from_headers(self, headers: Dict):
        """Met à jour les infos de rate limit depuis les headers"""
        try:
            if "X-App-Usage" in headers:
                usage = json.loads(headers["X-App-Usage"])
                call_count = usage.get("call_count", 0)
                total_calls = usage.get("total_calls", 200)
                
                if total_calls > 0:
                    self.rate_limit_remaining = max(0, total_calls - call_count)
                    
                    if self.rate_limit_remaining < 50:
                        logger.warning(f"⚠️ Rate limit restant: {self.rate_limit_remaining}")
                    
        except Exception as e:
            logger.debug(f"Could not parse rate limit headers: {e}")
    
    # ==================== WEBHOOK SUBSCRIPTION (MÉTHODE MANQUANTE) ====================
    
    async def subscribe_to_webhooks(
        self, 
        page_id: str, 
        access_token: str, 
        fields: List[str]
    ) -> Dict[str, Any]:
        """
        🔥 MÉTHODE MANQUANTE AJOUTÉE
        Souscrit aux webhooks Facebook pour une page
        """
        try:
            logger.info(f"🔔 Subscription webhook pour page {page_id}")
            logger.info(f"   Champs: {fields}")
            
            url = f"{self.base_url}/{page_id}/subscribed_apps"
            params = {
                "access_token": access_token,
                "subscribed_fields": ",".join(fields)
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, params=params)
                
                logger.info(f"📤 Webhook subscription HTTP: {response.status_code}")
                
                if response.status_code != 200:
                    error_text = response.text[:500]
                    logger.error(f"❌ Webhook subscription error: {error_text}")
                    return {
                        "success": False,
                        "error": f"HTTP {response.status_code}: {error_text}"
                    }
                
                result = response.json()
                
                if "error" in result:
                    error_msg = result["error"].get("message", "Unknown error")
                    logger.error(f"❌ Facebook webhook error: {error_msg}")
                    return {
                        "success": False,
                        "error": error_msg
                    }
                
                if result.get("success", False):
                    logger.info(f"✅ Webhooks souscrits avec succès pour {len(fields)} champs")
                    return {
                        "success": True,
                        "message": f"Webhooks souscrits pour {len(fields)} champs",
                        "fields": fields,
                        "raw_response": result
                    }
                else:
                    logger.warning(f"⚠️ Webhook subscription returned success=False")
                    return {
                        "success": False,
                        "error": "Facebook API returned success=False",
                        "raw_response": result
                    }
                
        except httpx.TimeoutException:
            logger.error("⏱️ Timeout lors de la subscription webhook")
            return {
                "success": False,
                "error": "Timeout Facebook API"
            }
        except Exception as e:
            logger.error(f"❌ Erreur subscription webhook: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    async def unsubscribe_from_webhooks(
        self, 
        page_id: str, 
        access_token: str
    ) -> Dict[str, Any]:
        """
        Désinscrit une page des webhooks
        """
        try:
            url = f"{self.base_url}/{page_id}/subscribed_apps"
            params = {"access_token": access_token}
            
            async with httpx.AsyncClient() as client:
                response = await client.delete(url, params=params)
                result = response.json()
                
                if "error" in result:
                    return {"success": False, "error": result["error"].get("message")}
                
                return {"success": True, "message": "Webhooks désinscrits"}
                
        except Exception as e:
            logger.error(f"❌ Erreur désinscription webhook: {e}")
            return {"success": False, "error": str(e)}
    
    # ==================== PAGE POSTS & COMMENTS ====================
    
    async def get_page_posts(
        self, 
        page_id: str, 
        access_token: str,
        limit: int = 100,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        fields: str = None
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        🔥 VERSION CORRIGÉE sans champs dépréciés
        """
        try:
            # ⭐⭐ CHAMPS SANS "type" ni .summary() qui sont dépréciés
            # ⭐⭐ UTILISEZ DES CHAMPS SIMPLES SEULEMENT
            if fields is None:
                fields = "id,message,story,created_time"
            
            params = {
                "access_token": access_token,
                "limit": min(limit, 100),
                "fields": fields
            }
            
            # Optionnel: ajouter since
            if since:
                params["since"] = int(since.timestamp())
            
            logger.info(f"🔄 get_page_posts SIMPLE: {page_id}")
            logger.info(f"   Fields: {fields}")
            
            # Faire la requête
            async with httpx.AsyncClient(timeout=30.0) as client:
                url = f"https://graph.facebook.com/v18.0/{page_id}/posts"
                response = await client.get(url, params=params)
                
                logger.info(f"📥 HTTP Status: {response.status_code}")
                
                if response.status_code != 200:
                    error_text = response.text[:500]
                    logger.error(f"❌ Facebook API Error: {error_text}")
                    return [], {}
                
                result = response.json()
                
                if "error" in result:
                    error_msg = result["error"].get("message", "Unknown")
                    logger.error(f"❌ Facebook API Error: {error_msg}")
                    return [], {}
                
                posts = result.get("data", [])
                paging = result.get("paging", {})
                
                logger.info(f"✅ {len(posts)} posts récupérés de Facebook")
                
                # DEBUG: Afficher quelques posts
                for i, post in enumerate(posts[:3]):
                    logger.info(f"   Post {i+1}: {post.get('id')}")
                    logger.info(f"      Has message: {'message' in post}")
                    logger.info(f"      Has story: {'story' in post}")
                    if post.get('message'):
                        logger.info(f"      Message: '{post['message'][:50]}...'")
                
                return posts, paging
                
        except Exception as e:
            logger.error(f"❌ Erreur get_page_posts: {e}", exc_info=True)
            return [], {}

    async def get_post_stats(self, post_id: str, access_token: str) -> Dict[str, Any]:
        """
        🔥 Récupère les statistiques d'un post séparément (likes, comments, shares)
        car les champs .summary() sont dépréciés dans la requête principale
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Récupérer les likes
                likes_url = f"https://graph.facebook.com/v18.0/{post_id}/likes"
                likes_params = {
                    "access_token": access_token,
                    "summary": "true",
                    "limit": 0
                }
                
                likes_response = await client.get(likes_url, params=likes_params)
                likes_data = likes_response.json() if likes_response.status_code == 200 else {}
                
                # Récupérer les comments
                comments_url = f"https://graph.facebook.com/v18.0/{post_id}/comments"
                comments_params = {
                    "access_token": access_token,
                    "summary": "true",
                    "limit": 0,
                    "filter": "stream"
                }
                
                comments_response = await client.get(comments_url, params=comments_params)
                comments_data = comments_response.json() if comments_response.status_code == 200 else {}
                
                # Récupérer les shares
                post_url = f"https://graph.facebook.com/v18.0/{post_id}"
                post_params = {
                    "access_token": access_token,
                    "fields": "shares"
                }
                
                post_response = await client.get(post_url, params=post_params)
                post_data = post_response.json() if post_response.status_code == 200 else {}
                
                # Extraire les counts
                likes_count = likes_data.get("summary", {}).get("total_count", 0)
                comments_count = comments_data.get("summary", {}).get("total_count", 0)
                shares_count = post_data.get("shares", {}).get("count", 0) if post_data.get("shares") else 0
                
                return {
                    "likes_count": likes_count,
                    "comments_count": comments_count,
                    "shares_count": shares_count,
                    "raw": {
                        "likes": likes_data,
                        "comments": comments_data,
                        "post": post_data
                    }
                }
                
        except Exception as e:
            logger.error(f"❌ Erreur get_post_stats: {e}")
            return {
                "likes_count": 0,
                "comments_count": 0,
                "shares_count": 0
            }
    
    async def get_post_comments(
        self, 
        post_id: str, 
        access_token: str,
        limit: int = 100,
        filter_by: str = "stream",
        order: str = "chronological",
        include_replies: bool = False
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        🔥 Récupère les commentaires d'un post (version corrigée)
        """
        try:
            # Champs avec from pour avoir le nom de l'utilisateur
            fields = "id,message,created_time,from{id,name}"
            
            params = {
                "fields": fields,
                "access_token": access_token,
                "limit": min(limit, 100),
                "filter": filter_by,
                "order": order
            }
            
            logger.info(f"🔍 Récupération commentaires post {post_id}")
            
            # Faire la requête directement
            async with httpx.AsyncClient(timeout=30.0) as client:
                url = f"https://graph.facebook.com/v18.0/{post_id}/comments"
                response = await client.get(url, params=params)
                
                logger.info(f"📥 Commentaires HTTP Status: {response.status_code}")
                
                if response.status_code != 200:
                    error_text = response.text[:200]
                    logger.error(f"❌ Facebook API Error (comments): {error_text}")
                    return [], {}
                
                result = response.json()
                
                if "error" in result:
                    error_msg = result["error"].get("message", "Unknown")
                    logger.error(f"❌ Facebook API Error (comments): {error_msg}")
                    return [], {}
                
                comments = result.get("data", [])
                paging = result.get("paging", {})
                
                logger.info(f"📊 {len(comments)} commentaires récupérés pour post {post_id}")
                
                return comments, paging
                
        except Exception as e:
            logger.error(f"❌ Erreur récupération commentaires: {e}", exc_info=True)
            return [], {}
    
    # ==================== LIVE VIDEOS ====================
    
    async def get_live_videos(
        self, 
        page_id: str, 
        access_token: str,
        limit: int = 20,
        status: str = None
    ) -> List[Dict[str, Any]]:
        """
        Récupère les lives vidéos d'une page
        """
        try:
            fields = "id,title,description,status,creation_time,live_views,stream_url,permalink_url"
            
            params = {
                "fields": fields,
                "access_token": access_token,
                "limit": min(limit, 50)
            }
            
            if status:
                params["status"] = status
            
            async with httpx.AsyncClient() as client:
                url = f"{self.base_url}/{page_id}/live_videos"
                response = await client.get(url, params=params)
                result = response.json()
                
                if "error" in result:
                    logger.error(f"❌ Erreur récupération lives: {result['error'].get('message')}")
                    return []
                
                return result.get("data", [])
                
        except Exception as e:
            logger.error(f"❌ Erreur get_live_videos: {e}")
            return []
    
    async def get_live_comments(
        self, 
        video_id: str, 
        access_token: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Récupère les commentaires d'un live vidéo
        """
        return await self.get_post_comments(video_id, access_token, limit=limit)
    
    # ==================== PAGE & USER INFO ====================
    
    async def get_user_pages(self, user_access_token: str) -> List[Dict[str, Any]]:
        """
        🔥 Récupère les pages de l'utilisateur
        """
        try:
            async with httpx.AsyncClient() as client:
                url = f"https://graph.facebook.com/v18.0/me/accounts"
                params = {
                    "access_token": user_access_token,
                    "fields": "id,name,access_token,category,fan_count,picture{url}",
                    "limit": 200
                }
                
                response = await client.get(url, params=params)
                result = response.json()
                
                if "error" in result:
                    logger.error(f"❌ Erreur récupération pages: {result['error'].get('message')}")
                    return []
                
                pages = result.get("data", [])
                
                formatted_pages = []
                for page in pages:
                    formatted = {
                        "id": page.get("id"),
                        "name": page.get("name", "Sans nom"),
                        "access_token": page.get("access_token", ""),
                        "category": page.get("category"),
                        "fan_count": page.get("fan_count", 0),
                        "profile_pic_url": page.get("picture", {}).get("data", {}).get("url") 
                            if page.get("picture") else None
                    }
                    formatted_pages.append(formatted)
                
                logger.info(f"✅ {len(formatted_pages)} pages récupérées")
                return formatted_pages
                
        except Exception as e:
            logger.error(f"❌ Erreur récupération pages: {e}")
            return []
    
    async def debug_token(self, input_token: str, app_id: str, app_secret: str) -> Dict[str, Any]:
        """
        🔥 Débogue un token Facebook
        """
        try:
            app_token = f"{app_id}|{app_secret}"
            
            async with httpx.AsyncClient() as client:
                url = f"https://graph.facebook.com/v18.0/debug_token"
                params = {
                    "input_token": input_token,
                    "access_token": app_token
                }
                
                response = await client.get(url, params=params)
                result = response.json()
                
                data = result.get("data", {})
                
                return {
                    "is_valid": data.get("is_valid", False),
                    "user_id": data.get("user_id"),
                    "app_id": data.get("app_id"),
                    "scopes": data.get("scopes", []),
                    "expires_at": data.get("expires_at"),
                    "expires_at_human": datetime.fromtimestamp(data.get("expires_at", 0)).isoformat() 
                        if data.get("expires_at", 0) > 0 else None
                }
                
        except Exception as e:
            logger.error(f"❌ Erreur debug_token: {e}")
            return {"is_valid": False, "error": str(e)}
    
    async def get_page_info(
        self, 
        page_id: str, 
        access_token: str,
        fields: str = "id,name,category,fan_count,picture{url},cover{source}"
    ) -> Dict[str, Any]:
        """
        Récupère les informations d'une page
        """
        try:
            params = {
                "access_token": access_token,
                "fields": fields
            }
            
            async with httpx.AsyncClient() as client:
                url = f"{self.base_url}/{page_id}"
                response = await client.get(url, params=params)
                result = response.json()
                
                if "error" in result:
                    logger.error(f"❌ Erreur récupération page info: {result['error'].get('message')}")
                    return {}
                
                return result
                
        except Exception as e:
            logger.error(f"❌ Erreur get_page_info: {e}")
            return {}
    
    # ==================== POST DETAILS ====================
    
    async def get_post_details(
        self, 
        post_id: str, 
        access_token: str,
        fields: str = "id,message,story,created_time,attachments{media}"
    ) -> Dict[str, Any]:
        """
        Récupère les détails d'un post spécifique
        """
        try:
            params = {
                "access_token": access_token,
                "fields": fields
            }
            
            async with httpx.AsyncClient() as client:
                url = f"{self.base_url}/{post_id}"
                response = await client.get(url, params=params)
                result = response.json()
                
                if "error" in result:
                    logger.error(f"❌ Erreur récupération post: {result['error'].get('message')}")
                    return {}
                
                return result
                
        except Exception as e:
            logger.error(f"❌ Erreur get_post_details: {e}")
            return {}
    
    async def get_live_details(
        self, 
        video_id: str, 
        access_token: str,
        fields: str = "id,title,description,status,creation_time,end_time,live_views,stream_url,permalink_url"
    ) -> Dict[str, Any]:
        """
        Récupère les détails d'un live vidéo
        """
        return await self.get_post_details(video_id, access_token, fields)
    
    # ==================== COMMENT REPLY ====================
    
    async def reply_to_comment(
        self, 
        comment_id: str, 
        access_token: str, 
        message: str
    ) -> Dict[str, Any]:
        """
        Répond à un commentaire Facebook
        """
        try:
            url = f"{self.base_url}/{comment_id}/comments"
            params = {
                "access_token": access_token,
                "message": message
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(url, params=params)
                result = response.json()
                
                if "error" in result:
                    return {
                        "success": False,
                        "error": result["error"].get("message", "Unknown error")
                    }
                
                return {
                    "success": True,
                    "comment_id": result.get("id"),
                    "message": "Réponse envoyée"
                }
                
        except Exception as e:
            logger.error(f"❌ Erreur réponse commentaire: {e}")
            return {"success": False, "error": str(e)}
    
    async def reply_to_post(
        self, 
        post_id: str, 
        access_token: str, 
        message: str
    ) -> Dict[str, Any]:
        """
        Commenter directement sur un post
        """
        return await self.reply_to_comment(post_id, access_token, message)
    
    # ==================== SYNC OPERATIONS ====================
    
    async def sync_page_data(
        self,
        page_id: str,
        access_token: str,
        posts_limit: int = 50,
        since: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        🔥 Synchronisation complète d'une page
        """
        try:
            # Récupérer les posts
            posts, paging = await self.get_page_posts(
                page_id, access_token, 
                limit=posts_limit, since=since
            )
            
            total_comments = 0
            
            # Pour chaque post, récupérer les stats et commentaires
            for post in posts:
                post_id = post.get("id")
                if post_id:
                    # Récupérer les stats (likes, comments, shares)
                    stats = await self.get_post_stats(post_id, access_token)
                    post["stats"] = stats
                    
                    # Récupérer les commentaires si besoin
                    if stats["comments_count"] > 0:
                        comments, _ = await self.get_post_comments(
                            post_id, access_token,
                            limit=min(stats["comments_count"], 100)
                        )
                        post["comments"] = comments
                        total_comments += len(comments)
            
            return {
                "success": True,
                "page_id": page_id,
                "posts": posts,
                "total_posts": len(posts),
                "total_comments": total_comments,
                "has_more": "next" in paging if paging else False
            }
            
        except Exception as e:
            logger.error(f"❌ Erreur sync_page_data: {e}")
            return {
                "success": False,
                "error": str(e),
                "page_id": page_id,
                "posts": [],
                "total_posts": 0,
                "total_comments": 0
            }


# 🔥 Instance singleton
try:
    # Créer l'instance
    facebook_graph_service = FacebookGraphAPIService(api_version="v18.0", timeout=30)
    
    # Alias
    facebook_graph_api = facebook_graph_service
    
    logger.info("✅ FacebookGraphAPIService initialisé avec succès")
    
except Exception as e:
    logger.critical(f"💥 Échec initialisation FacebookGraphAPIService: {e}")
    
    # Service dégradé pour éviter les crashs
    class DegradedFacebookGraphAPI:
        def __init__(self):
            self.base_url = "NOT_CONFIGURED"
            logger.warning("⚠️ FacebookGraphAPI en mode dégradé")
        
        async def get_page_posts(self, *args, **kwargs):
            logger.error("❌ FacebookGraphAPI non configuré")
            return [], {}
        
        async def get_post_comments(self, *args, **kwargs):
            logger.error("❌ FacebookGraphAPI non configuré")
            return [], {}
        
        async def sync_page_data(self, *args, **kwargs):
            return {
                "success": False,
                "error": "Service non configuré",
                "posts": [],
                "total_posts": 0,
                "total_comments": 0
            }
        
        async def subscribe_to_webhooks(self, *args, **kwargs):
            return {
                "success": False,
                "error": "Service non configuré"
            }
        
        async def close(self):
            pass
        
        async def __aenter__(self):
            return self
        
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            await self.close()
    
    facebook_graph_service = DegradedFacebookGraphAPI()
    facebook_graph_api = facebook_graph_service