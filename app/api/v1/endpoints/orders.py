# app/api/v1/endpoints/orders.py
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import List, Optional
from uuid import UUID
import logging

from sqlalchemy.orm import Session

from app.db import get_db
from app.core.security import get_current_seller
from app.models.order import Order
from app.schemas.order import (
    OrderCreate, OrderUpdate, OrderResponse, OrderListResponse,
    OrderStatsResponse, OrderFilter, OrderStatus,
    MessengerConfirmationRequest, OrderConfirmationResponse
)
from app.services.order_service import OrderService

router = APIRouter()
logger = logging.getLogger(__name__)

# ============ ORDER MANAGEMENT ENDPOINTS ============

@router.get("/orders", response_model=OrderListResponse)
async def get_orders(
    status: Optional[OrderStatus] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    needs_delivery: Optional[bool] = Query(None),
    source: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Récupère les commandes du vendeur avec filtres
    """
    try:
        # Construire les filtres
        filters = OrderFilter(
            status=status,
            start_date=start_date,
            end_date=end_date,
            needs_delivery=needs_delivery,
            source=source
        )
        
        # Récupérer les commandes
        order_service = OrderService(db)
        orders, total = order_service.get_orders(
            seller_id=current_seller.id,
            filters=filters,
            limit=limit,
            offset=offset
        )
        
        return OrderListResponse(
            count=len(orders),
            total=total,
            orders=orders
        )
        
    except Exception as e:
        logger.error(f"❌ Erreur récupération commandes: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# ============ FACEBOOK INTEGRATION ENDPOINTS ============

@router.get("/orders/from-facebook", response_model=OrderListResponse)
async def get_facebook_orders(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Récupère les commandes créées depuis Facebook
    """
    try:
        order_service = OrderService(db)
        filters = OrderFilter(source="facebook_comment")
        
        orders, total = order_service.get_orders(
            seller_id=current_seller.id,
            filters=filters,
            limit=limit,
            offset=offset
        )
        
        return OrderListResponse(
            count=len(orders),
            total=total,
            orders=orders
        )
        
    except Exception as e:
        logger.error(f"❌ Erreur récupération commandes Facebook: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============ SPECIFIC ORDER ENDPOINTS ============

@router.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order_detail(
    order_id: UUID,
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Récupère une commande spécifique
    """
    try:
        order_service = OrderService(db)
        order = order_service.get_order_by_id(order_id, current_seller.id)
        
        if not order:
            raise HTTPException(
                status_code=404,
                detail="Commande non trouvée"
            )
        
        return order
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erreur récupération commande {order_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/orders/number/{order_number}", response_model=OrderResponse)
async def get_order_by_number(
    order_number: str,
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Récupère une commande par son numéro
    """
    try:
        order_service = OrderService(db)
        order = order_service.get_order_by_number(order_number, current_seller.id)
        
        if not order:
            raise HTTPException(
                status_code=404,
                detail="Commande non trouvée"
            )
        
        return order
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erreur récupération commande {order_number}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/orders", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    order_data: OrderCreate,
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Crée une nouvelle commande
    """
    try:
        order_service = OrderService(db)
        order = order_service.create_order(current_seller.id, order_data)
        
        return order
        
    except Exception as e:
        logger.error(f"❌ Erreur création commande: {e}", exc_info=True)
        raise HTTPException(
            status_code=400,
            detail=f"Erreur création commande: {str(e)}"
        )

@router.put("/orders/{order_id}", response_model=OrderResponse)
async def update_order(
    order_id: UUID,
    order_update: OrderUpdate,
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Met à jour une commande
    """
    try:
        order_service = OrderService(db)
        order = order_service.get_order_by_id(order_id, current_seller.id)
        
        if not order:
            raise HTTPException(status_code=404, detail="Commande non trouvée")
        
        # Mettre à jour les champs
        update_data = order_update.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(order, field, value)
        
        order.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(order)
        
        return order
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Erreur mise à jour commande {order_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/orders/{order_id}/status", response_model=OrderResponse)
async def update_order_status(
    order_id: UUID,
    status: OrderStatus = Query(...),
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Met à jour le statut d'une commande
    """
    try:
        order_service = OrderService(db)
        order = order_service.update_order_status(order_id, current_seller.id, status)
        
        if not order:
            raise HTTPException(status_code=404, detail="Commande non trouvée")
        
        return order
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erreur mise à jour statut commande {order_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============ ORDER STATISTICS ENDPOINTS ============

@router.get("/orders/stats", response_model=OrderStatsResponse)
async def get_order_statistics(
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Récupère les statistiques des commandes
    """
    try:
        order_service = OrderService(db)
        stats = order_service.get_order_stats(current_seller.id)
        
        return OrderStatsResponse(**stats)
        
    except Exception as e:
        logger.error(f"❌ Erreur récupération statistiques: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============ MESSENGER CONFIRMATION ENDPOINTS ============

@router.post("/orders/{order_id}/confirm", response_model=OrderConfirmationResponse)
async def confirm_order_via_messenger(
    order_id: UUID,
    confirmation_data: MessengerConfirmationRequest,
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Confirme une commande via Messenger avec les coordonnées du client
    """
    try:
        order_service = OrderService(db)
        order = order_service.get_order_by_id(order_id, current_seller.id)
        
        if not order:
            raise HTTPException(status_code=404, detail="Commande non trouvée")
        
        # Mettre à jour les coordonnées depuis Messenger
        confirmed_details = confirmation_data.confirmed_details
        
        if "customer_phone" in confirmed_details:
            order.customer_phone = confirmed_details["customer_phone"]
        
        if "shipping_address" in confirmed_details:
            order.shipping_address = confirmed_details["shipping_address"]
        
        if "customer_name" in confirmed_details:
            order.customer_name = confirmed_details["customer_name"]
        
        # Passer en statut "preparing"
        order.status = OrderStatus.PREPARING
        order.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(order)
        
        logger.info(f"✅ Commande {order.order_number} confirmée via Messenger")
        
        return OrderConfirmationResponse(
            success=True,
            order_id=order.id,
            order_number=order.order_number,
            confirmed_at=datetime.utcnow(),
            next_steps="La commande est en préparation. Vous serez contacté pour la livraison."
        )
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Erreur confirmation commande {order_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============ TEST ENDPOINT ============

@router.get("/orders/test/create-sample")
async def create_sample_order(
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Crée une commande d'exemple pour tester
    """
    try:
        from app.schemas.order import OrderCreate, OrderItemCreate
        
        order_data = OrderCreate(
            customer_name="Jean Dupont",
            customer_phone="0331234567",
            shipping_address="123 Rue de Paris, 75001 Paris",
            needs_delivery=True,
            items=[
                OrderItemCreate(
                    product_name="iPhone 15 Pro",
                    product_code="APL-IP15P",
                    quantity=1,
                    unit_price=1199.99
                ),
                OrderItemCreate(
                    product_name="Chargeur USB-C",
                    product_code="ACC-PB20",
                    quantity=2,
                    unit_price=29.99
                )
            ],
            source="facebook_comment",
            source_id="fb_test_123"
        )
        
        order_service = OrderService(db)
        order = order_service.create_order(current_seller.id, order_data)
        
        return {
            "success": True,
            "message": "Commande d'exemple créée",
            "order_number": order.order_number,
            "total_amount": float(order.total_amount)
        }
        
    except Exception as e:
        logger.error(f"❌ Erreur création commande test: {e}")
        raise HTTPException(status_code=500, detail=str(e))