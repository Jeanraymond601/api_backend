from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_
from app.models.user import User
from app.models.seller import Seller
from typing import List, Optional
import uuid

class JointureService:
    
    @staticmethod
    def get_seller_with_user(db: Session, user_id: uuid.UUID) -> Optional[Seller]:
        """
        Récupère un seller avec toutes ses infos user via jointure
        """
        return (db.query(Seller)
                .options(joinedload(Seller.user))
                .filter(Seller.user_id == user_id)
                .first())
    
    @staticmethod
    def get_user_with_seller(db: Session, user_id: uuid.UUID) -> Optional[User]:
        """
        Récupère un user avec son profil seller via jointure
        """
        return (db.query(User)
                .options(joinedload(User.seller))
                .filter(User.id == user_id)
                .first())
    
    @staticmethod
    def get_all_sellers_with_users(db: Session, skip: int = 0, limit: int = 100) -> List[Seller]:
        """
        Récupère tous les sellers avec leurs users
        """
        return (db.query(Seller)
                .options(joinedload(Seller.user))
                .filter(User.role == "Vendeur")  # Jointure implicite
                .offset(skip)
                .limit(limit)
                .all())
    
    @staticmethod
    def get_all_vendeurs_with_details(db: Session) -> List[dict]:
        """
        Récupère tous les vendeurs avec détails complets (jointure explicite)
        Retourne un dictionnaire avec les champs des deux tables
        """
        results = (db.query(
                    User.id,
                    User.full_name,
                    User.email,
                    User.telephone,
                    User.adresse,
                    User.statut,
                    User.created_at,
                    Seller.company_name,
                    Seller.abonnement_type,
                    Seller.abonnement_status
                )
                .join(Seller, User.id == Seller.user_id)
                .filter(User.role == "Vendeur")
                .all())
        
        return [
            {
                "user_id": result.id,
                "full_name": result.full_name,
                "email": result.email,
                "telephone": result.telephone,
                "adresse": result.adresse,
                "statut": result.statut,
                "created_at": result.created_at,
                "company_name": result.company_name,
                "abonnement_type": result.abonnement_type,
                "abonnement_status": result.abonnement_status
            }
            for result in results
        ]
    
    @staticmethod
    def get_vendeur_by_email(db: Session, email: str) -> Optional[dict]:
        """
        Récupère un vendeur par email avec jointure
        """
        result = (db.query(
                    User.id,
                    User.full_name,
                    User.email,
                    User.telephone,
                    User.adresse,
                    User.role,
                    User.statut,
                    Seller.id.label("seller_id"),
                    Seller.company_name,
                    Seller.abonnement_type
                )
                .join(Seller, User.id == Seller.user_id)
                .filter(and_(User.email == email, User.role == "Vendeur"))
                .first())
        
        if result:
            return {
                "user_id": result.id,
                "seller_id": result.seller_id,
                "full_name": result.full_name,
                "email": result.email,
                "telephone": result.telephone,
                "adresse": result.adresse,
                "role": result.role,
                "statut": result.statut,
                "company_name": result.company_name,
                "abonnement_type": result.abonnement_type
            }
        return None
    
    @staticmethod
    def verify_seller_creation(db: Session, user_id: uuid.UUID) -> bool:
        """
        Vérifie si un seller a bien été créé pour un user
        """
        seller = db.query(Seller).filter(Seller.user_id == user_id).first()
        return seller is not None