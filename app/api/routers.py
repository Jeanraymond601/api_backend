from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging
import uuid
import re
from sqlalchemy.orm import Session

# IMPORT depuis db.py
from app.db import get_db, SessionLocal
from app.models import FacebookComment, FacebookPage, Order
from app.services.order_builder import OrderBuilderService
from app.core.security import get_current_seller

logger = logging.getLogger(__name__)

# Create main API router
api_router = APIRouter()

# --- IntentDetector simplifié ---
class IntentResult:
    def __init__(self):
        self.intent_type = 'unknown'
        self.confidence = 0.0
        self.sentiment = 'neutral'
        self.extracted_products = []
        self.entities = {}

class IntentDetector:
    async def analyze_comment(self, text: str) -> IntentResult:
        """Analyse simplifiée d'un commentaire"""
        result = IntentResult()
        text_lower = text.lower() if text else ""
        
        # Détection d'intention basique
        purchase_keywords = ['je veux', 'je voudrais', 'commander', 'acheter', 'prendre', 'donnez-moi', 'prix']
        question_keywords = ['comment', 'quand', 'où', 'pourquoi', 'quel', 'quelle', '?']
        complaint_keywords = ['problème', 'erreur', 'faux', 'mauvais', 'pas content', 'réclamation']
        
        purchase_score = sum(1 for kw in purchase_keywords if kw in text_lower)
        question_score = sum(1 for kw in question_keywords if kw in text_lower)
        complaint_score = sum(1 for kw in complaint_keywords if kw in text_lower)
        
        scores = {
            'purchase': purchase_score,
            'question': question_score,
            'complaint': complaint_score
        }
        
        max_intent = max(scores, key=scores.get)
        max_score = scores[max_intent]
        
        if max_score > 0:
            result.intent_type = max_intent
            result.confidence = min(max_score / 3, 1.0)
        else:
            result.intent_type = 'unknown'
            result.confidence = 0.0
        
        # Détection de sentiment
        positive_words = ['super', 'excellent', 'génial', 'parfait', 'merci']
        negative_words = ['nul', 'horrible', 'déçu', 'déception', 'mauvais']
        
        positive_count = sum(1 for word in positive_words if word in text_lower)
        negative_count = sum(1 for word in negative_words if word in text_lower)
        
        if positive_count > negative_count:
            result.sentiment = 'positive'
        elif negative_count > positive_count:
            result.sentiment = 'negative'
        else:
            result.sentiment = 'neutral'
        
        # Extraction de produits
        result.extracted_products = self._extract_products(text_lower)
        
        # Entités basiques
        result.entities = {
            'prices': re.findall(r'(\d+)\s*(?:€|euro|euros|mg|ar|mga)', text_lower),
            'quantities': re.findall(r'\b(\d+)\b', text_lower)
        }
        
        logger.info(f"Analyse commentaire: intent={result.intent_type}, confidence={result.confidence}")
        return result
    
    def _extract_products(self, text: str) -> List[Dict[str, Any]]:
        """Extrait les produits mentionnés"""
        products = []
        
        # Pattern: "2 pizzas" ou "pizza x 2"
        patterns = [
            r'(\d+)\s*([\w\s]+?)(?:s|$)',  # "2 pizzas"
            r'([\w\s]+?)\s*x\s*(\d+)',     # "pizza x 2"
        ]
        
        for pattern in patterns:
            matches = re.finditer(pattern, text)
            for match in matches:
                try:
                    quantity = int(match.group(1)) if match.group(1).isdigit() else 1
                    product_name = match.group(2).strip()
                    
                    if len(product_name) > 2:
                        products.append({
                            'name': product_name,
                            'quantity': quantity,
                            'code': product_name[:3].upper().replace(' ', ''),
                            'price': None,
                            'confidence': 0.7
                        })
                except:
                    continue
        
        return products

# Initialiser les services
intent_detector = IntentDetector()
order_builder_config = {
    'product_database': {},
    'stock_service': None,
    'price_matching_threshold': 60
}
order_builder = OrderBuilderService(order_builder_config)

# --- FONCTIONS HELPER ---

def determine_priority(intent_result) -> str:
    """Détermine la priorité du commentaire"""
    if intent_result.intent_type == 'purchase' and intent_result.confidence > 0.7:
        return 'high'
    elif intent_result.intent_type == 'complaint':
        return 'high'
    elif intent_result.intent_type == 'purchase':
        return 'medium'
    else:
        return 'low'

def prepare_nlp_result_for_order_builder(comment, intent_result) -> Dict[str, Any]:
    """Prépare les données NLP pour OrderBuilder"""
    return {
        'text': comment.message or "",
        'intent': intent_result.intent_type,
        'intent_confidence': intent_result.confidence,
        'language': 'fr',
        'order_items': [
            {
                'product': p['name'],
                'quantity': p['quantity'],
                'confidence': intent_result.confidence * 0.8
            }
            for p in intent_result.extracted_products
        ],
        'phone_numbers': [],
        'emails': [],
        'address': {},
        'prices': [],
        'total_amount': None  # À calculer par OrderBuilder
    }

async def create_order_from_structure(order_structure: Dict[str, Any], 
                                     comment: FacebookComment, 
                                     seller_id: str, 
                                     db: Session) -> Optional[Order]:
    """Crée une commande en base depuis la structure OrderBuilder"""
    try:
        # Préparer les données pour la création
        order_data = {
            'id': uuid.uuid4(),
            'order_number': order_structure.get('order_id', f"CMD-{uuid.uuid4().hex[:8]}"),
            'seller_id': seller_id,
            'customer_name': comment.user_name or "Client Facebook",
            'customer_phone': None,
            'total_amount': order_structure.get('total_amount', 0),
            'currency': 'MGA',
            'status': 'pending',
            'source': 'facebook_comment',
            'source_id': comment.facebook_comment_id,
            'metadata': order_structure.get('metadata', {}),
            'items_json': order_structure.get('items', []),
            'created_at': datetime.utcnow()
        }
        
        # Créer la commande
        order = Order(**order_data)
        db.add(order)
        db.flush()
        
        logger.info(f"✅ Commande créée: {order.order_number}")
        return order
        
    except Exception as e:
        logger.error(f"❌ Erreur création commande: {e}")
        return None

async def send_order_confirmation(order: Order, comment: FacebookComment, page_id: str):
    """Envoie une confirmation de commande en réponse au commentaire"""
    try:
        # Récupérer la page
        db = SessionLocal()
        try:
            page = db.query(FacebookPage).filter(FacebookPage.page_id == page_id).first()
            
            if not page or not page.page_access_token:
                logger.warning(f"Page {page_id} ou token non trouvé")
                return
            
            # Construire le message
            message = f"""✅ Commande confirmée !

Commande: {order.order_number}
Montant: {order.total_amount} MGA
Statut: En traitement

📩 Nous vous contactons bientôt pour finaliser la commande.
Merci pour votre confiance ! 🙏"""
            
            logger.info(f"Message à envoyer: {message}")
            
            # NOTE: Ici tu dois implémenter l'envoi réel via Facebook API
            # await facebook_service.reply_to_comment(...)
            
        finally:
            db.close()
        
    except Exception as e:
        logger.error(f"❌ Erreur envoi confirmation: {e}")

# --- ROUTES ---

@api_router.post("/facebook/comments/process", tags=["facebook"])
async def process_facebook_comments(
    comment_ids: Optional[List[str]] = None,
    post_id: Optional[str] = None,
    page_id: Optional[str] = None,
    auto_create_orders: bool = True,
    background_tasks: BackgroundTasks = None,
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Traite les commentaires Facebook pour détecter les intentions d'achat
    et créer des commandes automatiquement.
    """
    try:
        # Construire la requête de base
        query = db.query(FacebookComment).filter(
            FacebookComment.seller_id == current_seller.id,
            FacebookComment.status == 'new'
        )
        
        # Appliquer les filtres
        if comment_ids:
            query = query.filter(FacebookComment.facebook_comment_id.in_(comment_ids))
        if post_id:
            query = query.filter(FacebookComment.post_id == post_id)
        if page_id:
            page = db.query(FacebookPage).filter(
                FacebookPage.page_id == page_id,
                FacebookPage.seller_id == current_seller.id
            ).first()
            if page:
                query = query.filter(FacebookComment.page_id == str(page.id))
        
        # Récupérer les commentaires
        comments = query.order_by(FacebookComment.created_at.desc()).limit(100).all()
        
        if not comments:
            return {
                "success": True,
                "message": "Aucun commentaire à traiter",
                "processed": 0,
                "orders_created": 0
            }
        
        logger.info(f"🔄 Début traitement de {len(comments)} commentaires")
        
        results = []
        orders_created = 0
        
        for comment in comments:
            try:
                # Analyser l'intention
                intent_result = await intent_detector.analyze_comment(comment.message or "")
                
                # Mettre à jour le commentaire
                comment.status = 'processing'
                comment.intent = intent_result.intent_type
                comment.sentiment = intent_result.sentiment
                comment.priority = determine_priority(intent_result)
                
                if intent_result.extracted_products:
                    comment.detected_code_article = ','.join(
                        [p['code'] for p in intent_result.extracted_products]
                    )
                    comment.detected_quantity = sum(
                        p['quantity'] for p in intent_result.extracted_products
                    )
                else:
                    comment.detected_code_article = None
                    comment.detected_quantity = 0
                
                # Créer une commande si c'est une intention d'achat
                if (intent_result.intent_type == 'purchase' and 
                    intent_result.confidence > 0.6 and 
                    auto_create_orders and
                    intent_result.extracted_products):
                    
                    # Préparer les données
                    nlp_result = prepare_nlp_result_for_order_builder(comment, intent_result)
                    
                    # Construire la structure de commande
                    try:
                        order_structure = order_builder.build_order_structure(nlp_result)
                        
                        # Créer la commande
                        if order_structure and order_structure.get('metadata', {}).get('extraction_confidence', 0) > 0.5:
                            order = await create_order_from_structure(
                                order_structure=order_structure,
                                comment=comment,
                                seller_id=current_seller.id,
                                db=db
                            )
                            
                            if order:
                                orders_created += 1
                                comment.status = 'processed'
                                comment.intent = 'ORDER_CREATED'
                                
                                # Tâche en arrière-plan
                                if background_tasks:
                                    background_tasks.add_task(
                                        send_order_confirmation,
                                        order=order,
                                        comment=comment,
                                        page_id=page_id or comment.page_id
                                    )
                    except Exception as e:
                        logger.error(f"Erreur OrderBuilder: {e}")
                
                db.add(comment)
                results.append({
                    "comment_id": comment.facebook_comment_id,
                    "intent": intent_result.intent_type,
                    "confidence": intent_result.confidence,
                    "products": intent_result.extracted_products,
                    "status": comment.status
                })
                
            except Exception as e:
                logger.error(f"❌ Erreur traitement commentaire {comment.id}: {e}")
                comment.status = 'error'
                db.add(comment)
                results.append({
                    "comment_id": comment.facebook_comment_id,
                    "error": str(e),
                    "status": "error"
                })
        
        db.commit()
        
        return {
            "success": True,
            "message": f"Traitement terminé: {len(results)} commentaires traités",
            "processed": len(results),
            "orders_created": orders_created,
            "results": results
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Erreur traitement batch commentaires: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/facebook/comments/{comment_id}/process", tags=["facebook"])
async def process_single_comment(
    comment_id: str,
    auto_create_order: bool = True,
    background_tasks: BackgroundTasks = None,
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Traite un commentaire Facebook spécifique.
    """
    try:
        # Récupérer le commentaire
        comment = db.query(FacebookComment).filter(
            FacebookComment.facebook_comment_id == comment_id,
            FacebookComment.seller_id == current_seller.id
        ).first()
        
        if not comment:
            raise HTTPException(status_code=404, detail="Commentaire non trouvé")
        
        logger.info(f"🔄 Traitement commentaire: {comment_id}")
        
        # Analyser l'intention
        intent_result = await intent_detector.analyze_comment(comment.message or "")
        
        # Mettre à jour le commentaire
        comment.status = 'processing'
        comment.intent = intent_result.intent_type
        comment.sentiment = intent_result.sentiment
        comment.priority = determine_priority(intent_result)
        
        if intent_result.extracted_products:
            comment.detected_code_article = ','.join(
                [p['code'] for p in intent_result.extracted_products]
            )
            comment.detected_quantity = sum(
                p['quantity'] for p in intent_result.extracted_products
            )
        else:
            comment.detected_code_article = None
            comment.detected_quantity = 0
        
        result = {
            "comment_id": comment.facebook_comment_id,
            "intent": intent_result.intent_type,
            "confidence": intent_result.confidence,
            "sentiment": intent_result.sentiment,
            "products": intent_result.extracted_products,
            "entities": intent_result.entities
        }
        
        # Créer une commande si c'est une intention d'achat
        if (intent_result.intent_type == 'purchase' and 
            intent_result.confidence > 0.6 and 
            auto_create_order and
            intent_result.extracted_products):
            
            # Préparer les données
            nlp_result = prepare_nlp_result_for_order_builder(comment, intent_result)
            
            # Construire la structure de commande
            try:
                order_structure = order_builder.build_order_structure(nlp_result)
                
                # Créer la commande
                if order_structure and order_structure.get('metadata', {}).get('extraction_confidence', 0) > 0.5:
                    order = await create_order_from_structure(
                        order_structure=order_structure,
                        comment=comment,
                        seller_id=current_seller.id,
                        db=db
                    )
                    
                    if order:
                        comment.status = 'processed'
                        comment.intent = 'ORDER_CREATED'
                        result["order_created"] = True
                        result["order_id"] = str(order.id)
                        result["order_number"] = order.order_number
                        
                        # Tâche en arrière-plan
                        if background_tasks:
                            background_tasks.add_task(
                                send_order_confirmation,
                                order=order,
                                comment=comment,
                                page_id=comment.page_id
                            )
            except Exception as e:
                logger.error(f"Erreur OrderBuilder: {e}")
        
        db.add(comment)
        db.commit()
        
        result["final_status"] = comment.status
        
        return {
            "success": True,
            "message": "Commentaire traité avec succès",
            "result": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Erreur traitement commentaire {comment_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/facebook/comments/pending", tags=["facebook"])
async def get_pending_comments(
    page_id: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Récupère les commentaires en attente de traitement.
    """
    try:
        query = db.query(FacebookComment).filter(
            FacebookComment.seller_id == current_seller.id,
            FacebookComment.status.in_(['new', 'processing'])
        )
        
        if page_id:
            page = db.query(FacebookPage).filter(
                FacebookPage.page_id == page_id,
                FacebookPage.seller_id == current_seller.id
            ).first()
            if page:
                query = query.filter(FacebookComment.page_id == str(page.id))
        
        if priority:
            query = query.filter(FacebookComment.priority == priority)
        
        comments = query.order_by(
            FacebookComment.created_at.desc()
        ).limit(limit).all()
        
        return {
            "success": True,
            "count": len(comments),
            "comments": [
                {
                    "id": c.facebook_comment_id,
                    "message": c.message,
                    "user_name": c.user_name,
                    "post_id": c.post_id,
                    "status": c.status,
                    "intent": c.intent,
                    "priority": c.priority,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                    "has_products": c.detected_code_article is not None
                }
                for c in comments
            ]
        }
        
    except Exception as e:
        logger.error(f"❌ Erreur récupération commentaires: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- Routes supplémentaires (optionnelles) ---

@api_router.get("/facebook/comments/processed", tags=["facebook"])
async def get_processed_comments(
    page_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """Récupère les commentaires déjà traités"""
    try:
        query = db.query(FacebookComment).filter(
            FacebookComment.seller_id == current_seller.id,
            FacebookComment.status == 'processed'
        )
        
        if page_id:
            page = db.query(FacebookPage).filter(
                FacebookPage.page_id == page_id,
                FacebookPage.seller_id == current_seller.id
            ).first()
            if page:
                query = query.filter(FacebookComment.page_id == str(page.id))
        
        comments = query.order_by(FacebookComment.updated_at.desc()).limit(limit).all()
        
        return {
            "success": True,
            "count": len(comments),
            "comments": [
                {
                    "id": c.facebook_comment_id,
                    "message": c.message[:100] + "..." if len(c.message) > 100 else c.message,
                    "user_name": c.user_name,
                    "intent": c.intent,
                    "status": c.status,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                    "updated_at": c.updated_at.isoformat() if c.updated_at else None
                }
                for c in comments
            ]
        }
        
    except Exception as e:
        logger.error(f"❌ Erreur récupération commentaires traités: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/facebook/health", tags=["facebook"])
async def facebook_health_check():
    """Vérifie l'état du service Facebook"""
    return {
        "status": "healthy",
        "services": {
            "intent_detector": "active",
            "order_builder": "active" if order_builder else "inactive",
            "database": "connected"
        }
    }

# --- ROUTES DE SECOURS OCR ---

@api_router.get("/ocr/health", tags=["ocr-nlp"])
async def ocr_health_fallback():
    return {
        "status": "ocr_service_loading",
        "message": "Le service OCR est en cours de démarrage ou non disponible."
    }

@api_router.post("/ocr/text", tags=["ocr-nlp"])
async def ocr_endpoint_fallback():
    raise HTTPException(
        status_code=503,
        detail="Service OCR temporairement indisponible."
    )

# --- Export ---
__all__ = ["api_router"]