from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db import get_db
from app.services.jointure_service import JointureService
from typing import List
import uuid

router = APIRouter(prefix="/jointure", tags=["jointures"])

@router.get("/vendeurs/avec-details")
def get_all_vendeurs_with_details(db: Session = Depends(get_db)):
    """
    Récupère tous les vendeurs avec leurs détails complets
    """
    vendeurs = JointureService.get_all_vendeurs_with_details(db)
    return {"vendeurs": vendeurs, "count": len(vendeurs)}

@router.get("/vendeur/{user_id}")
def get_vendeur_by_id(user_id: uuid.UUID, db: Session = Depends(get_db)):
    """
    Récupère un vendeur spécifique avec tous ses détails
    """
    vendeur = JointureService.get_seller_with_user(db, user_id)
    if not vendeur:
        raise HTTPException(status_code=404, detail="Vendeur non trouvé")
    return vendeur

@router.get("/vendeur/email/{email}")
def get_vendeur_by_email(email: str, db: Session = Depends(get_db)):
    """
    Récupère un vendeur par son email
    """
    vendeur = JointureService.get_vendeur_by_email(db, email)
    if not vendeur:
        raise HTTPException(status_code=404, detail="Vendeur non trouvé")
    return vendeur

@router.get("/verifier-creation/{user_id}")
def verify_seller_creation(user_id: uuid.UUID, db: Session = Depends(get_db)):
    """
    Vérifie si un seller a bien été créé pour un user
    """
    est_cree = JointureService.verify_seller_creation(db, user_id)
    return {
        "user_id": user_id,
        "seller_cree": est_cree,
        "message": "Seller créé avec succès" if est_cree else "Aucun seller trouvé"
    }