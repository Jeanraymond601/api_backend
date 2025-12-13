import hashlib
import hmac
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from app.core.config import settings

logger = logging.getLogger(__name__)

class FacebookWebhookService:
    def __init__(self):
        self.app_secret = settings.FACEBOOK_APP_SECRET
        self.verify_token = settings.FACEBOOK_WEBHOOK_VERIFY_TOKEN
    
    def verify_signature(self, payload: bytes, signature: str) -> bool:
        """
        Vérifie la signature HMAC du webhook Facebook
        """
        if not signature or not self.app_secret:
            return False
        
        expected_signature = hmac.new(
            self.app_secret.encode('utf-8'),
            payload,
            hashlib.sha1
        ).hexdigest()
        
        return hmac.compare_digest(f"sha1={expected_signature}", signature)
    
    def parse_webhook_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse un événement webhook Facebook
        """
        parsed_event = {
            "object_type": None,
            "event_type": None,
            "page_id": None,
            "data": {}
        }
        
        try:
            for entry in event.get("entry", []):
                # Récupérer l'ID de la page
                parsed_event["page_id"] = entry.get("id")
                
                for change in entry.get("changes", []):
                    parsed_event["object_type"] = change.get("field")
                    
                    # Commentaires
                    if parsed_event["object_type"] == "feed":
                        value = change.get("value")
                        if value:
                            if value.get("item") == "comment":
                                parsed_event["event_type"] = "comment"
                                parsed_event["data"] = {
                                    "comment_id": value.get("comment_id"),
                                    "post_id": value.get("post_id"),
                                    "parent_id": value.get("parent_id"),
                                    "sender_id": value.get("sender_id"),
                                    "sender_name": value.get("sender_name"),
                                    "message": value.get("message"),
                                    "verb": value.get("verb")  # add, edit, remove
                                }
                    
                    # Messages
                    elif parsed_event["object_type"] == "conversations":
                        parsed_event["event_type"] = "message"
                    
                    # Live videos
                    elif parsed_event["object_type"] == "live_videos":
                        value = change.get("value")
                        parsed_event["event_type"] = "live_video"
                        parsed_event["data"] = {
                            "live_id": value.get("id"),
                            "status": value.get("status")
                        }
                
                # Messages directs (messaging)
                for messaging in entry.get("messaging", []):
                    parsed_event["event_type"] = "messaging"
                    parsed_event["data"] = messaging
        
        except Exception as e:
            logger.error(f"Erreur parsing webhook: {e}")
        
        return parsed_event