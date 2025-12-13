# app/services/facebook_graph_api.py
import httpx
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import json
import asyncio
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

class FacebookGraphAPIService:
    """
    Service pour interagir avec l'API Graph de Facebook
    Documentation: https://developers.facebook.com/docs/graph-api
    """
    
    BASE_URL = "https://graph.facebook.com/v18.0"
    
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)
    
    async def close(self):
        """Ferme le client HTTP"""
        await self.client.aclose()
    
    async def make_request(
        self, 
        method: str, 
        endpoint: str, 
        params: Dict = None, 
        data: Dict = None,
        headers: Dict = None
    ) -> Dict:
        """
        Fait une requête à l'API Graph Facebook
        """
        url = f"{self.BASE_URL}/{endpoint.lstrip('/')}"
        
        default_params = params or {}
        default_headers = headers or {}
        
        try:
            if method.upper() == "GET":
                response = await self.client.get(
                    url, 
                    params=default_params,
                    headers=default_headers
                )
            elif method.upper() == "POST":
                response = await self.client.post(
                    url,
                    params=default_params,
                    json=data,
                    headers=default_headers
                )
            elif method.upper() == "DELETE":
                response = await self.client.delete(
                    url,
                    params=default_params,
                    headers=default_headers
                )
            else:
                raise ValueError(f"Méthode non supportée: {method}")
            
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPStatusError as e:
            error_data = {}
            try:
                error_data = e.response.json()
            except:
                error_data = {"error": {"message": str(e)}}
            
            logger.error(f"Erreur API Facebook {method} {endpoint}: {error_data}")
            raise Exception(f"Facebook API Error: {error_data.get('error', {}).get('message', str(e))}")
            
        except Exception as e:
            logger.error(f"Erreur requête Facebook {method} {endpoint}: {e}")
            raise
    
    # ==================== USER & AUTH ====================
    
    async def get_user_info(self, access_token: str, user_id: str = "me") -> Dict:
        """
        Récupère les informations de l'utilisateur Facebook
        """
        return await self.make_request(
            "GET",
            f"{user_id}",
            params={
                "fields": "id,name,email,first_name,last_name,middle_name,"
                         "picture{url},location,gender,age_range,birthday,"
                         "link,website,verified",
                "access_token": access_token
            }
        )
    
    async def get_user_pages(self, access_token: str) -> List[Dict]:
        """
        Récupère la liste des pages de l'utilisateur
        """
        result = await self.make_request(
            "GET",
            "me/accounts",
            params={
                "fields": "id,name,access_token,category,category_list,"
                         "picture{url},cover{source},fan_count,about,"
                         "description,emails,link,location,phone,"
                         "website,tasks,verification_status,"
                         "is_always_open,is_owned,is_published,"
                         "global_brand_page_name,best_page",
                "access_token": access_token,
                "limit": 200
            }
        )
        return result.get("data", [])
    
    async def debug_token(self, input_token: str, app_token: str) -> Dict:
        """
        Débogue un token Facebook
        """
        return await self.make_request(
            "GET",
            "debug_token",
            params={
                "input_token": input_token,
                "access_token": app_token
            }
        )
    
    # ==================== PAGE MANAGEMENT ====================
    
    async def get_page_info(self, page_id: str, access_token: str) -> Dict:
        """
        Récupère les informations détaillées d'une page
        """
        return await self.make_request(
            "GET",
            page_id,
            params={
                "fields": "id,name,access_token,category,category_list,"
                         "picture{url},cover{source},fan_count,about,"
                         "description,emails,link,location,phone,"
                         "website,tasks,verification_status,"
                         "is_always_open,is_owned,is_published,"
                         "global_brand_page_name,best_page,"
                         "engagement{count},followers_count,"
                         "new_like_count,rating_count,"
                         "talking_about_count,were_here_count,"
                         "checkins,impressum,products,"
                         "restaurant_services,restaurant_specialties,"
                         "hours,single_line_address,store_location_descriptor,"
                         "price_range,parking,payment_options,"
                         "attire,culinary_team,general_info,"
                         "general_manager,personal_info,"
                         "personal_interests,pharma_safety_info,"
                         "public_transit",
                "access_token": access_token
            }
        )
    
    async def get_page_insights(
        self, 
        page_id: str, 
        access_token: str,
        metric: str = "page_engaged_users,page_impressions",
        period: str = "day",
        since: Optional[datetime] = None,
        until: Optional[datetime] = None
    ) -> List[Dict]:
        """
        Récupère les insights d'une page
        """
        params = {
            "metric": metric,
            "period": period,
            "access_token": access_token
        }
        
        if since:
            params["since"] = int(since.timestamp())
        if until:
            params["until"] = int(until.timestamp())
        
        result = await self.make_request(
            "GET",
            f"{page_id}/insights",
            params=params
        )
        return result.get("data", [])
    
    async def get_page_posts(
        self, 
        page_id: str, 
        access_token: str,
        limit: int = 100,
        since: Optional[datetime] = None,
        fields: str = None
    ) -> List[Dict]:
        """
        Récupère les posts d'une page
        """
        default_fields = (
            "id,message,created_time,updated_time,story,"
            "full_picture,picture,permalink_url,status_type,"
            "type,is_hidden,is_expired,is_published,is_instagram_eligible,"
            "is_popular,attachments{media_type,title,url,target,description},"
            "comments.limit(0).summary(true),"
            "likes.limit(0).summary(true),"
            "shares,reactions.limit(0).summary(true)"
        )
        
        params = {
            "fields": fields or default_fields,
            "access_token": access_token,
            "limit": limit
        }
        
        if since:
            params["since"] = int(since.timestamp())
        
        result = await self.make_request(
            "GET",
            f"{page_id}/posts",
            params=params
        )
        return result.get("data", [])
    
    async def publish_post(
        self,
        page_id: str,
        access_token: str,
        message: str = None,
        link: str = None,
        photos: List[str] = None,
        scheduled_publish_time: Optional[datetime] = None,
        published: bool = True
    ) -> Dict:
        """
        Publie un post sur une page
        """
        data = {}
        
        if message:
            data["message"] = message
        if link:
            data["link"] = link
        if scheduled_publish_time:
            data["scheduled_publish_time"] = int(scheduled_publish_time.timestamp())
            data["published"] = False
        else:
            data["published"] = published
        
        endpoint = f"{page_id}/feed"
        
        # Si photos, upload d'abord les photos
        if photos:
            photo_ids = []
            for photo_url in photos:
                photo_id = await self.upload_photo(
                    page_id, 
                    photo_url, 
                    access_token,
                    published=False
                )
                if photo_id:
                    photo_ids.append(photo_id)
            
            if photo_ids:
                if len(photo_ids) == 1:
                    data["attached_media"] = json.dumps([{"media_fbid": photo_ids[0]}])
                else:
                    # Pour plusieurs photos, créer un album
                    album_id = await self.create_album(
                        page_id,
                        "Post photos",
                        access_token
                    )
                    if album_id:
                        for photo_id in photo_ids:
                            await self.add_photo_to_album(
                                album_id,
                                photo_id,
                                access_token
                            )
                        data["attached_media"] = json.dumps([{"media_fbid": photo_ids[0]}])
        
        return await self.make_request(
            "POST",
            endpoint,
            params={"access_token": access_token},
            data=data
        )
    
    async def delete_post(self, post_id: str, access_token: str) -> bool:
        """
        Supprime un post
        """
        try:
            await self.make_request(
                "DELETE",
                post_id,
                params={"access_token": access_token}
            )
            return True
        except:
            return False
    
    # ==================== COMMENTS ====================
    
    async def get_post_comments(
        self, 
        post_id: str, 
        access_token: str,
        limit: int = 100,
        filter_by: str = "stream",
        order: str = "chronological"
    ) -> List[Dict]:
        """
        Récupère les commentaires d'un post
        """
        result = await self.make_request(
            "GET",
            f"{post_id}/comments",
            params={
                "fields": "id,message,created_time,from{id,name,picture{url}},"
                         "like_count,comment_count,parent,attachment,"
                         "message_tags,is_hidden,user_likes",
                "access_token": access_token,
                "limit": limit,
                "filter": filter_by,
                "order": order
            }
        )
        return result.get("data", [])
    
    async def get_comment_replies(
        self, 
        comment_id: str, 
        access_token: str,
        limit: int = 50
    ) -> List[Dict]:
        """
        Récupère les réponses à un commentaire
        """
        result = await self.make_request(
            "GET",
            f"{comment_id}/comments",
            params={
                "fields": "id,message,created_time,from{id,name},like_count",
                "access_token": access_token,
                "limit": limit
            }
        )
        return result.get("data", [])
    
    async def post_comment(
        self, 
        post_id: str, 
        access_token: str,
        message: str,
        attachment_id: str = None,
        attachment_url: str = None
    ) -> Dict:
        """
        Poste un commentaire sur un post
        """
        data = {"message": message}
        
        if attachment_id:
            data["attachment_id"] = attachment_id
        elif attachment_url:
            data["attachment_url"] = attachment_url
        
        return await self.make_request(
            "POST",
            f"{post_id}/comments",
            params={"access_token": access_token},
            data=data
        )
    
    async def send_comment_reply(
        self, 
        comment_id: str, 
        message: str,
        access_token: str
    ) -> Dict:
        """
        Répond à un commentaire
        """
        return await self.make_request(
            "POST",
            f"{comment_id}/comments",
            params={"access_token": access_token},
            data={"message": message}
        )
    
    async def hide_comment(self, comment_id: str, access_token: str, hide: bool = True) -> bool:
        """
        Cache ou affiche un commentaire
        """
        try:
            await self.make_request(
                "POST",
                comment_id,
                params={"access_token": access_token},
                data={"is_hidden": hide}
            )
            return True
        except:
            return False
    
    async def like_comment(self, comment_id: str, access_token: str) -> bool:
        """
        Like un commentaire
        """
        try:
            await self.make_request(
                "POST",
                f"{comment_id}/likes",
                params={"access_token": access_token}
            )
            return True
        except:
            return False
    
    # ==================== MESSENGER ====================
    
    async def send_message(
        self,
        page_id: str,
        recipient_id: str,
        message_text: str = None,
        access_token: str = None,
        messaging_type: str = "RESPONSE",
        tag: str = None,
        quick_replies: List[Dict] = None,
        attachment: Dict = None
    ) -> Dict:
        """
        Envoie un message Messenger
        """
        data = {
            "recipient": {"id": recipient_id},
            "messaging_type": messaging_type
        }
        
        if message_text:
            data["message"] = {"text": message_text}
        elif attachment:
            data["message"] = {"attachment": attachment}
        
        if tag:
            data["tag"] = tag
        
        if quick_replies:
            if "message" not in data:
                data["message"] = {}
            data["message"]["quick_replies"] = quick_replies
        
        return await self.make_request(
            "POST",
            f"{page_id}/messages",
            params={"access_token": access_token},
            data=data
        )
    
    async def send_template_message(
        self,
        page_id: str,
        recipient_id: str,
        template: Dict,
        access_token: str
    ) -> Dict:
        """
        Envoie un message template Messenger
        """
        data = {
            "recipient": {"id": recipient_id},
            "message": {"attachment": {
                "type": "template",
                "payload": template
            }}
        }
        
        return await self.make_request(
            "POST",
            f"{page_id}/messages",
            params={"access_token": access_token},
            data=data
        )
    
    async def get_user_profile(
        self, 
        user_id: str, 
        page_id: str, 
        access_token: str
    ) -> Dict:
        """
        Récupère le profil Messenger d'un utilisateur
        """
        return await self.make_request(
            "GET",
            user_id,
            params={
                "fields": "first_name,last_name,profile_pic,locale,timezone,gender",
                "access_token": access_token
            }
        )
    
    async def mark_message_as_read(
        self, 
        recipient_id: str, 
        page_id: str,
        access_token: str
    ) -> bool:
        """
        Marque un message comme lu
        """
        try:
            await self.make_request(
                "POST",
                f"{page_id}/messages",
                params={"access_token": access_token},
                data={
                    "recipient": {"id": recipient_id},
                    "sender_action": "mark_seen"
                }
            )
            return True
        except:
            return False
    
    async def typing_on(
        self, 
        recipient_id: str, 
        page_id: str,
        access_token: str
    ) -> bool:
        """
        Active l'indicateur "typing" (écriture en cours)
        """
        try:
            await self.make_request(
                "POST",
                f"{page_id}/messages",
                params={"access_token": access_token},
                data={
                    "recipient": {"id": recipient_id},
                    "sender_action": "typing_on"
                }
            )
            return True
        except:
            return False
    
    # ==================== LIVE VIDEOS ====================
    
    async def get_live_videos(
        self, 
        page_id: str, 
        access_token: str,
        limit: int = 50,
        broadcast_status: str = None
    ) -> List[Dict]:
        """
        Récupère les lives vidéos d'une page
        """
        params = {
            "fields": "id,title,description,status,creation_time,"
                     "scheduled_start_time,live_views,end_time,"
                     "permalink_url,from,embed_html,length,"
                     "source,broadcast_start_time,"
                     "comments.limit(10){id,message,from,created_time}",
            "access_token": access_token,
            "limit": limit
        }
        
        if broadcast_status:
            params["broadcast_status"] = broadcast_status
        
        result = await self.make_request(
            "GET",
            f"{page_id}/live_videos",
            params=params
        )
        return result.get("data", [])
    
    async def get_live_video_insights(
        self, 
        video_id: str, 
        access_token: str,
        metric: str = "total_video_views"
    ) -> List[Dict]:
        """
        Récupère les insights d'une vidéo live
        """
        result = await self.make_request(
            "GET",
            f"{video_id}/video_insights",
            params={
                "metric": metric,
                "access_token": access_token
            }
        )
        return result.get("data", [])
    
    async def get_live_comments(
        self, 
        video_id: str, 
        access_token: str,
        limit: int = 100,
        filter_by: str = "stream",
        order: str = "chronological",
        since: Optional[datetime] = None
    ) -> List[Dict]:
        """
        Récupère les commentaires d'un live
        """
        params = {
            "fields": "id,message,created_time,from{id,name,picture{url}},"
                     "like_count,attachment",
            "access_token": access_token,
            "limit": limit,
            "filter": filter_by,
            "order": order
        }
        
        if since:
            params["since"] = int(since.timestamp())
        
        result = await self.make_request(
            "GET",
            f"{video_id}/comments",
            params=params
        )
        return result.get("data", [])
    
    async def create_live_video(
        self,
        page_id: str,
        access_token: str,
        title: str = None,
        description: str = None,
        scheduled_start_time: Optional[datetime] = None,
        status: str = "SCHEDULED_UNPUBLISHED",
        allow_bm_crossposting: bool = True
    ) -> Dict:
        """
        Crée un live vidéo
        """
        data = {
            "status": status,
            "allow_bm_crossposting": allow_bm_crossposting
        }
        
        if title:
            data["title"] = title
        if description:
            data["description"] = description
        if scheduled_start_time:
            data["planned_start_time"] = int(scheduled_start_time.timestamp())
        
        return await self.make_request(
            "POST",
            f"{page_id}/live_videos",
            params={"access_token": access_token},
            data=data
        )
    
    async def end_live_video(self, video_id: str, access_token: str) -> bool:
        """
        Termine un live vidéo
        """
        try:
            await self.make_request(
                "POST",
                video_id,
                params={"access_token": access_token},
                data={"end_live_video": True}
            )
            return True
        except:
            return False
    
    # ==================== MEDIA UPLOAD ====================
    
    async def upload_photo(
        self,
        page_id: str,
        photo_url: str,
        access_token: str,
        published: bool = True,
        caption: str = None
    ) -> Optional[str]:
        """
        Upload une photo sur une page
        """
        try:
            # Télécharger la photo d'abord
            async with httpx.AsyncClient() as client:
                photo_response = await client.get(photo_url)
                photo_response.raise_for_status()
                
                # Upload vers Facebook
                files = {"source": photo_response.content}
                data = {
                    "access_token": access_token,
                    "published": published
                }
                
                if caption:
                    data["caption"] = caption
                
                upload_response = await self.client.post(
                    f"{self.BASE_URL}/{page_id}/photos",
                    data=data,
                    files=files
                )
                upload_response.raise_for_status()
                
                result = upload_response.json()
                return result.get("id")
                
        except Exception as e:
            logger.error(f"Erreur upload photo: {e}")
            return None
    
    async def create_album(
        self,
        page_id: str,
        name: str,
        access_token: str,
        description: str = None,
        privacy: str = "{'value': 'EVERYONE'}"
    ) -> Optional[str]:
        """
        Crée un album photo
        """
        try:
            data = {
                "name": name,
                "privacy": privacy,
                "access_token": access_token
            }
            
            if description:
                data["description"] = description
            
            result = await self.make_request(
                "POST",
                f"{page_id}/albums",
                data=data
            )
            return result.get("id")
            
        except Exception as e:
            logger.error(f"Erreur création album: {e}")
            return None
    
    async def add_photo_to_album(
        self,
        album_id: str,
        photo_id: str,
        access_token: str
    ) -> bool:
        """
        Ajoute une photo à un album
        """
        try:
            await self.make_request(
                "POST",
                f"{album_id}/photos",
                params={"access_token": access_token},
                data={"photo_id": photo_id}
            )
            return True
        except:
            return False
    
    async def upload_video(
        self,
        page_id: str,
        video_url: str,
        access_token: str,
        title: str = None,
        description: str = None,
        published: bool = True
    ) -> Optional[str]:
        """
        Upload une vidéo
        """
        try:
            # Récupérer la taille de la vidéo
            async with httpx.AsyncClient() as client:
                head_response = await client.head(video_url)
                file_size = int(head_response.headers.get("content-length", 0))
                
                if file_size == 0:
                    logger.error("Taille vidéo inconnue")
                    return None
                
                # Start upload session
                start_data = {
                    "upload_phase": "start",
                    "file_size": file_size,
                    "access_token": access_token
                }
                
                start_response = await self.make_request(
                    "POST",
                    f"{page_id}/videos",
                    data=start_data
                )
                
                video_id = start_response.get("video_id")
                upload_session_id = start_response.get("upload_session_id")
                start_offset = start_response.get("start_offset", 0)
                end_offset = start_response.get("end_offset", file_size)
                
                if not video_id:
                    return None
                
                # Transfert en chunks
                chunk_size = 4 * 1024 * 1024  # 4MB
                current_offset = start_offset
                
                while current_offset < end_offset:
                    # Télécharger le chunk
                    headers = {
                        "Range": f"bytes={current_offset}-{min(current_offset + chunk_size - 1, end_offset - 1)}"
                    }
                    
                    chunk_response = await client.get(video_url, headers=headers)
                    chunk_response.raise_for_status()
                    
                    # Upload le chunk
                    transfer_data = {
                        "upload_phase": "transfer",
                        "upload_session_id": upload_session_id,
                        "start_offset": current_offset,
                        "access_token": access_token
                    }
                    
                    files = {
                        "video_file_chunk": chunk_response.content
                    }
                    
                    await self.client.post(
                        f"{self.BASE_URL}/{video_id}",
                        data=transfer_data,
                        files=files
                    )
                    
                    current_offset += chunk_size
                
                # Finir l'upload
                finish_data = {
                    "upload_phase": "finish",
                    "upload_session_id": upload_session_id,
                    "access_token": access_token
                }
                
                if title:
                    finish_data["title"] = title
                if description:
                    finish_data["description"] = description
                
                finish_data["published"] = published
                
                await self.make_request(
                    "POST",
                    str(video_id),
                    data=finish_data
                )
                
                return video_id
                
        except Exception as e:
            logger.error(f"Erreur upload vidéo: {e}")
            return None
    
    # ==================== WEBHOOK SUBSCRIPTION ====================
    
    async def subscribe_to_webhooks(
        self,
        page_id: str,
        access_token: str,
        subscribed_fields: List[str],
        callback_url: str
    ) -> Dict:
        """
        Souscrit une page aux webhooks
        """
        return await self.make_request(
            "POST",
            f"{page_id}/subscribed_apps",
            params={"access_token": access_token},
            data={
                "subscribed_fields": ",".join(subscribed_fields),
                "callback_url": callback_url
            }
        )
    
    async def unsubscribe_from_webhooks(
        self,
        page_id: str,
        access_token: str
    ) -> Dict:
        """
        Désouscrit une page des webhooks
        """
        return await self.make_request(
            "DELETE",
            f"{page_id}/subscribed_apps",
            params={"access_token": access_token}
        )
    
    async def get_webhook_subscriptions(
        self,
        page_id: str,
        access_token: str
    ) -> List[Dict]:
        """
        Récupère les subscriptions webhook d'une page
        """
        result = await self.make_request(
            "GET",
            f"{page_id}/subscribed_apps",
            params={
                "fields": "subscribed_fields,callback_url",
                "access_token": access_token
            }
        )
        return result.get("data", [])
    
    # ==================== BATCH REQUESTS ====================
    
    async def make_batch_request(
        self,
        requests: List[Dict],
        access_token: str,
        include_headers: bool = False
    ) -> List[Dict]:
        """
        Fait plusieurs requêtes en batch
        """
        batch = []
        for i, req in enumerate(requests):
            batch_request = {
                "method": req.get("method", "GET"),
                "relative_url": req["relative_url"],
                "name": req.get("name", f"request_{i}"),
                "omit_response_on_success": req.get("omit_response_on_success", False)
            }
            
            if "body" in req:
                batch_request["body"] = urlencode(req["body"])
            
            batch.append(batch_request)
        
        data = {
            "batch": json.dumps(batch),
            "include_headers": include_headers,
            "access_token": access_token
        }
        
        result = await self.make_request(
            "POST",
            "",
            data=data
        )
        
        return result
    
    # ==================== ANALYTICS & INSIGHTS ====================
    
    async def get_page_analytics(
        self,
        page_id: str,
        access_token: str,
        metric: str = "page_impressions,page_engaged_users",
        period: str = "day",
        date_preset: str = "last_28d"
    ) -> List[Dict]:
        """
        Récupère les analytics de page
        """
        return await self.make_request(
            "GET",
            f"{page_id}/insights",
            params={
                "metric": metric,
                "period": period,
                "date_preset": date_preset,
                "access_token": access_token
            }
        )
    
    async def get_post_analytics(
        self,
        post_id: str,
        access_token: str,
        metric: str = "post_impressions,post_engaged_users"
    ) -> List[Dict]:
        """
        Récupère les analytics d'un post
        """
        return await self.make_request(
            "GET",
            f"{post_id}/insights",
            params={
                "metric": metric,
                "access_token": access_token
            }
        )
    
    async def get_audience_insights(
        self,
        page_id: str,
        access_token: str
    ) -> Dict:
        """
        Récupère les insights audience
        """
        result = await self.make_request(
            "GET",
            f"{page_id}/insights",
            params={
                "metric": "page_fans,page_fans_city,page_fans_country,"
                         "page_fans_gender_age,page_fans_locale",
                "period": "lifetime",
                "access_token": access_token
            }
        )
        
        insights = {}
        for item in result.get("data", []):
            insights[item["name"]] = item.get("values", [])
        
        return insights
    
    # ==================== UTILITIES ====================
    
    async def get_app_info(self, app_id: str, app_secret: str) -> Dict:
        """
        Récupère les infos de l'app Facebook
        """
        return await self.make_request(
            "GET",
            f"{app_id}",
            params={
                "fields": "id,name,description,category,company,"
                         "platform,ios_bundle_id,android_key_hash,"
                         "webhooks,app_domains,contact_email",
                "access_token": f"{app_id}|{app_secret}"
            }
        )
    
    async def test_api_connection(self, access_token: str) -> bool:
        """
        Teste la connexion à l'API
        """
        try:
            await self.get_user_info(access_token)
            return True
        except:
            return False
    
    async def rate_limit_info(self, access_token: str) -> Dict:
        """
        Récupère les infos de rate limit
        """
        headers = {
            "X-App-Usage": "1",
            "X-Page-Usage": "1",
            "X-Business-Use-Case-Usage": "1"
        }
        
        result = await self.make_request(
            "GET",
            "me",
            params={"access_token": access_token},
            headers=headers
        )
        
        usage = {}
        for header_name in ["X-App-Usage", "X-Page-Usage", "X-Business-Use-Case-Usage"]:
            if header_name in self.client._transport._pool._connections[0]._response.headers:
                usage[header_name] = self.client._transport._pool._connections[0]._response.headers[header_name]
        
        return {
            "user_info": result,
            "rate_limits": usage
        }