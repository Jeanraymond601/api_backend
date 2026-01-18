# app/services/order_service.py
import logging
import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.models.order import Order, OrderItem
from app.schemas.order import (
    OrderCreate, OrderUpdate, OrderItemCreate, 
    OrderStatus, OrderSource, OrderFilter
)

logger = logging.getLogger(__name__)

class OrderService:
    """Service pour la gestion des commandes"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def generate_order_number(self, seller_id: uuid.UUID) -> str:
        """Génère un numéro de commande unique"""
        from app.models import Seller
        
        # Récupérer le préfixe du vendeur
        seller = self.db.query(Seller).filter(Seller.id == seller_id).first()
        prefix = seller.company_name[:3].upper() if seller and seller.company_name else "SHO"
        
        # Compter les commandes du vendeur
        order_count = self.db.query(Order).filter(Order.seller_id == seller_id).count()
        
        # Générer le numéro
        date_str = datetime.now().strftime("%Y%m%d")
        return f"{prefix}-{date_str}-{order_count + 1:04d}"
    
    def create_order(self, seller_id: uuid.UUID, order_data: OrderCreate) -> Order:
        """Crée une nouvelle commande"""
        try:
            # Générer le numéro de commande
            order_number = self.generate_order_number(seller_id)
            
            # Créer la commande
            order = Order(
                id=uuid.uuid4(),
                order_number=order_number,
                seller_id=seller_id,
                customer_name=order_data.customer_name,
                customer_phone=order_data.customer_phone,
                shipping_address=order_data.shipping_address,
                needs_delivery=order_data.needs_delivery,
                source=order_data.source,
                source_id=order_data.source_id,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            
            # Ajouter les items
            total_amount = 0
            for item_data in order_data.items:
                item_total = item_data.unit_price * item_data.quantity
                total_amount += item_total
                
                item = OrderItem(
                    id=uuid.uuid4(),
                    order_id=order.id,
                    product_id=item_data.product_id,
                    product_name=item_data.product_name,
                    product_code=item_data.product_code,
                    quantity=item_data.quantity,
                    unit_price=item_data.unit_price,
                    total_price=item_total,
                    created_at=datetime.utcnow()
                )
                order.items.append(item)
            
            order.total_amount = total_amount
            
            self.db.add(order)
            self.db.commit()
            self.db.refresh(order)
            
            logger.info(f"✅ Commande créée: {order.order_number} - {order.customer_name}")
            return order
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"❌ Erreur création commande: {e}")
            raise
    
    def create_order_from_facebook_comment(
        self, 
        seller_id: uuid.UUID,
        comment_id: str,
        customer_name: str,
        product_code: str,
        quantity: int = 1,
        unit_price: float = 0.0
    ) -> Optional[Order]:
        """Crée une commande depuis un commentaire Facebook"""
        try:
            # CORRECTION: Chercher le produit par code_article (pas code)
            from app.models import Product
            
            # Recherche 1: Par code_article uniquement
            product = self.db.query(Product).filter(
                Product.code_article == product_code  # <-- CORRECTION ICI
            ).first()
            
            # Recherche 2: Si non trouvé, chercher avec seller_id
            if not product:
                product = self.db.query(Product).filter(
                    Product.code_article == product_code,
                    Product.seller_id == seller_id
                ).first()
            
            # Recherche 3: Recherche partielle (au cas où)
            if not product:
                product = self.db.query(Product).filter(
                    Product.code_article.ilike(f"%{product_code}%")
                ).first()
            
            # Si produit trouvé
            if product:
                product_name = product.name
                actual_unit_price = product.price
                product_id = product.id
            else:
                # Produit non trouvé, on utilise les infos fournies
                product_name = product_code  # Utiliser le code comme nom
                actual_unit_price = unit_price
                product_id = None
                logger.warning(f"⚠️ Produit non trouvé: {product_code}")
            
            # Créer la commande
            order_data = OrderCreate(
                customer_name=customer_name,
                customer_phone="A confirmer",  # À confirmer via Messenger
                shipping_address=None,  # À confirmer via Messenger
                needs_delivery=True,
                items=[
                    OrderItemCreate(
                        product_id=product_id,
                        product_name=product_name,
                        product_code=product_code,
                        quantity=quantity,
                        unit_price=actual_unit_price
                    )
                ],
                source=OrderSource.FACEBOOK_COMMENT,
                source_id=comment_id
            )
            
            order = self.create_order(seller_id, order_data)
            logger.info(f"✅ Commande créée depuis commentaire {comment_id}: {order.order_number}")
            return order
            
        except Exception as e:
            logger.error(f"❌ Erreur création commande depuis commentaire: {e}")
            return None
    
    def create_order_from_facebook_data(
        self,
        seller_id: uuid.UUID,
        comment_id: str,
        customer_name: str,
        detected_items: List[Dict[str, Any]]
    ) -> Optional[Order]:
        """Crée une commande avec plusieurs items depuis des données Facebook"""
        try:
            from app.models import Product
            
            order_items = []
            
            for item in detected_items:
                product_code = item.get("code_article")
                quantity = item.get("quantity", 1)
                
                if not product_code:
                    continue
                
                # Rechercher le produit
                product = self.db.query(Product).filter(
                    Product.code_article == product_code,
                    Product.seller_id == seller_id
                ).first()
                
                if product:
                    order_items.append(OrderItemCreate(
                        product_id=product.id,
                        product_name=product.name,
                        product_code=product.code_article,
                        quantity=quantity,
                        unit_price=product.price
                    ))
                else:
                    # Produit non trouvé, créer un item avec les infos disponibles
                    order_items.append(OrderItemCreate(
                        product_id=None,
                        product_name=product_code,
                        product_code=product_code,
                        quantity=quantity,
                        unit_price=item.get("unit_price", 0.0)
                    ))
            
            if not order_items:
                logger.warning(f"⚠️ Aucun item valide pour la commande depuis {comment_id}")
                return None
            
            # Créer la commande
            order_data = OrderCreate(
                customer_name=customer_name,
                customer_phone="A confirmer",
                shipping_address=None,
                needs_delivery=True,
                items=order_items,
                source=OrderSource.FACEBOOK_COMMENT,
                source_id=comment_id
            )
            
            order = self.create_order(seller_id, order_data)
            logger.info(f"✅ Commande multi-items créée depuis {comment_id}: {order.order_number}")
            return order
            
        except Exception as e:
            logger.error(f"❌ Erreur création commande multi-items: {e}")
            return None
    
    def get_orders(
        self, 
        seller_id: uuid.UUID,
        filters: Optional[OrderFilter] = None,
        limit: int = 20,
        offset: int = 0
    ) -> tuple[List[Order], int]:
        """Récupère les commandes avec filtres"""
        query = self.db.query(Order).filter(Order.seller_id == seller_id)
        
        if filters:
            if filters.status:
                query = query.filter(Order.status == filters.status)
            if filters.start_date:
                query = query.filter(Order.created_at >= filters.start_date)
            if filters.end_date:
                query = query.filter(Order.created_at <= filters.end_date)
            if filters.needs_delivery is not None:
                query = query.filter(Order.needs_delivery == filters.needs_delivery)
            if filters.source:
                query = query.filter(Order.source == filters.source)
        
        total = query.count()
        orders = query.order_by(desc(Order.created_at)).offset(offset).limit(limit).all()
        
        return orders, total
    
    def get_order_by_id(self, order_id: uuid.UUID, seller_id: uuid.UUID) -> Optional[Order]:
        """Récupère une commande par ID"""
        return self.db.query(Order).filter(
            Order.id == order_id,
            Order.seller_id == seller_id
        ).first()
    
    def get_order_by_number(self, order_number: str, seller_id: uuid.UUID) -> Optional[Order]:
        """Récupère une commande par numéro"""
        return self.db.query(Order).filter(
            Order.order_number == order_number,
            Order.seller_id == seller_id
        ).first()
    
    def update_order_status(
        self, 
        order_id: uuid.UUID, 
        seller_id: uuid.UUID, 
        status: OrderStatus
    ) -> Optional[Order]:
        """Met à jour le statut d'une commande"""
        order = self.get_order_by_id(order_id, seller_id)
        if not order:
            return None
        
        order.status = status
        order.updated_at = datetime.utcnow()
        
        self.db.commit()
        self.db.refresh(order)
        
        logger.info(f"📝 Statut commande {order.order_number} mis à jour: {status}")
        return order
    
    def update_order(
        self,
        order_id: uuid.UUID,
        seller_id: uuid.UUID,
        update_data: OrderUpdate
    ) -> Optional[Order]:
        """Met à jour une commande"""
        order = self.get_order_by_id(order_id, seller_id)
        if not order:
            return None
        
        # Mettre à jour les champs fournis
        update_dict = update_data.dict(exclude_unset=True)
        for field, value in update_dict.items():
            if hasattr(order, field):
                setattr(order, field, value)
        
        order.updated_at = datetime.utcnow()
        
        self.db.commit()
        self.db.refresh(order)
        
        logger.info(f"📝 Commande {order.order_number} mise à jour")
        return order
    
    def get_orders_from_facebook(self, seller_id: uuid.UUID) -> List[Order]:
        """Récupère toutes les commandes créées depuis Facebook"""
        return self.db.query(Order).filter(
            Order.seller_id == seller_id,
            Order.source == OrderSource.FACEBOOK_COMMENT
        ).order_by(desc(Order.created_at)).all()
    
    def get_order_stats(self, seller_id: uuid.UUID) -> Dict[str, Any]:
        """Récupère les statistiques des commandes"""
        stats = {}
        
        # Total commandes et montant
        total_query = self.db.query(
            func.count(Order.id).label("total_orders"),
            func.coalesce(func.sum(Order.total_amount), 0).label("total_amount")
        ).filter(Order.seller_id == seller_id)
        
        total_result = total_query.first()
        stats["total_orders"] = total_result.total_orders or 0
        stats["total_amount"] = float(total_result.total_amount or 0)
        
        # Commandes par statut
        for status in OrderStatus:
            count = self.db.query(func.count(Order.id)).filter(
                Order.seller_id == seller_id,
                Order.status == status
            ).scalar()
            stats[f"{status.value}_orders"] = count or 0
        
        # Valeur moyenne des commandes
        stats["average_order_value"] = (
            stats["total_amount"] / stats["total_orders"] 
            if stats["total_orders"] > 0 else 0
        )
        
        # Commandes par source
        sources_query = self.db.query(
            Order.source,
            func.count(Order.id).label("count")
        ).filter(
            Order.seller_id == seller_id
        ).group_by(Order.source).all()
        
        stats["orders_by_source"] = {
            source: count for source, count in sources_query
        }
        
        return stats
    
    def get_facebook_orders_stats(self, seller_id: uuid.UUID) -> Dict[str, Any]:
        """Statistiques spécifiques aux commandes Facebook"""
        # Commandes Facebook
        fb_orders = self.db.query(Order).filter(
            Order.seller_id == seller_id,
            Order.source == OrderSource.FACEBOOK_COMMENT
        )
        
        total_fb_orders = fb_orders.count()
        
        # Montant total des commandes Facebook
        fb_total = self.db.query(
            func.coalesce(func.sum(Order.total_amount), 0)
        ).filter(
            Order.seller_id == seller_id,
            Order.source == OrderSource.FACEBOOK_COMMENT
        ).scalar()
        
        # Commandes Facebook par statut
        fb_by_status = {}
        for status in OrderStatus:
            count = self.db.query(func.count(Order.id)).filter(
                Order.seller_id == seller_id,
                Order.source == OrderSource.FACEBOOK_COMMENT,
                Order.status == status
            ).scalar()
            fb_by_status[status.value] = count or 0
        
        return {
            "total_facebook_orders": total_fb_orders,
            "facebook_orders_amount": float(fb_total or 0),
            "facebook_orders_by_status": fb_by_status,
            "average_facebook_order_value": (
                float(fb_total) / total_fb_orders if total_fb_orders > 0 else 0
            )
        }