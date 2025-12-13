from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, func
from uuid import UUID
from typing import List, Optional, Dict, Any, Tuple
import logging
from datetime import datetime

from app.services.geocoding_service import geocoding_service
from app.models import User, Driver
from app.schemas import (
    DriverCreateSimple,  # Pour create_driver
    UserUpdate,         # Pour update_driver
    DriverUpdate        # Pour update_driver
)
from app.core.security import get_password_hash

logger = logging.getLogger(__name__)

class DriverService:
    
    @staticmethod
    async def create_driver(
        db: Session, 
        driver_data: DriverCreateSimple,
        seller_id: UUID,
        current_user_id: UUID
    ) -> tuple[Optional[User], Optional[Driver], str]:
        """
        Crée un livreur pour le vendeur connecté
        """
        try:
            # Convertir en dict
            data_dict = driver_data.dict()
            
            # Vérifier si l'email existe déjà
            existing_user = db.query(User).filter(
                User.email == data_dict["email"]
            ).first()
            
            if existing_user:
                return None, None, "Email déjà utilisé"
            
            # Vérifier que le vendeur existe
            seller_user = db.query(User).filter(
                User.id == seller_id
            ).first()
            
            if not seller_user:
                return None, None, "Vendeur non trouvé"
            
            # Vérifier que le vendeur a le bon rôle
            if seller_user.role.upper() not in ["VENDEUR", "VENDOR", "Vendeur"]:
                return None, None, f"L'utilisateur n'est pas un vendeur. Rôle: {seller_user.role}"
            
            # Créer l'utilisateur (LIVREUR)
            hashed_password = get_password_hash(data_dict["password"])
            
            user = User(
                full_name=data_dict["full_name"],
                email=data_dict["email"],
                telephone=data_dict["telephone"],
                adresse=data_dict["adresse"],
                role="LIVREUR",
                statut=data_dict.get("statut", "en_attente"),
                password=hashed_password,
                is_active=True
            )
            
            db.add(user)
            db.flush()
            
            # Déterminer la zone de livraison
            zone_livraison = data_dict.get("zone_livraison")
            if not zone_livraison or zone_livraison == "":
                try:
                    zone_livraison = geocoding_service.extract_zone_from_address(
                        data_dict["adresse"]
                    )
                    logger.info(f"Zone géocodée: {zone_livraison}")
                except Exception as e:
                    logger.error(f"Erreur géocodage: {e}")
                    # Fallback: utiliser le début de l'adresse
                    zone_livraison = data_dict["adresse"][:50] if len(data_dict["adresse"]) > 50 else data_dict["adresse"]
            
            # Créer le driver
            driver = Driver(
                user_id=user.id,
                seller_id=seller_id,
                zone_livraison=zone_livraison,
                disponibilite=True
            )
            
            db.add(driver)
            db.commit()
            
            logger.info(f"Livreur créé: {user.email} pour le vendeur {seller_id}")
            return user, driver, "Livreur créé avec succès"
            
        except Exception as e:
            db.rollback()
            logger.error(f"Erreur création livreur: {e}")
            return None, None, f"Erreur création: {str(e)}"
    
    @staticmethod
    async def update_driver(
        db: Session,
        driver_id: UUID,
        user_data: Optional[UserUpdate],
        driver_data: Optional[DriverUpdate],
        seller_id: UUID
    ) -> tuple[Optional[Driver], str]:
        """
        Met à jour les informations d'un livreur
        """
        try:
            # Récupérer le driver avec vérification du seller_id
            driver = db.query(Driver).filter(
                and_(
                    Driver.id == driver_id,
                    Driver.seller_id == seller_id
                )
            ).first()
            
            if not driver:
                return None, "Livreur non trouvé"
            
            # Mettre à jour l'utilisateur si des données sont fournies
            if user_data:
                user = db.query(User).filter(User.id == driver.user_id).first()
                if not user:
                    return None, "Utilisateur non trouvé"
                
                # Mettre à jour les champs fournis
                update_dict = user_data.dict(exclude_unset=True)
                for field, value in update_dict.items():
                    if value is not None:
                        if field == "adresse":
                            old_address = user.adresse
                            setattr(user, field, value)
                            # Mettre à jour la zone de livraison si l'adresse change
                            if value != old_address:
                                try:
                                    driver.zone_livraison = geocoding_service.extract_zone_from_address(value)
                                    logger.info(f"Zone mise à jour pour nouvelle adresse: {driver.zone_livraison}")
                                except Exception as e:
                                    logger.error(f"Erreur géocodage lors de la mise à jour: {e}")
                        else:
                            setattr(user, field, value)
            
            # Mettre à jour le driver si des données sont fournies
            if driver_data:
                update_dict = driver_data.dict(exclude_unset=True)
                for field, value in update_dict.items():
                    if value is not None:
                        setattr(driver, field, value)
            
            # Mettre à jour la date de modification
            driver.updated_at = datetime.utcnow()
            
            db.commit()
            db.refresh(driver)
            
            logger.info(f"Livreur mis à jour: {driver.id}")
            return driver, "Livreur mis à jour avec succès"
            
        except Exception as e:
            db.rollback()
            logger.error(f"Erreur mise à jour livreur: {e}")
            return None, f"Erreur mise à jour: {str(e)}"
    
    @staticmethod
    async def toggle_driver_status(
        db: Session,
        driver_id: UUID,
        action: str,  # "activate", "suspend", "delete"
        seller_id: UUID
    ) -> tuple[Optional[User], str]:
        """
        Active, suspend ou supprime (soft delete) un livreur
        """
        try:
            # Récupérer le driver avec vérification du seller_id
            driver = db.query(Driver).filter(
                and_(
                    Driver.id == driver_id,
                    Driver.seller_id == seller_id
                )
            ).first()
            
            if not driver:
                return None, "Livreur non trouvé"
            
            user = db.query(User).filter(User.id == driver.user_id).first()
            if not user:
                return None, "Utilisateur non trouvé"
            
            if action == "activate":
                user.statut = "actif"
                user.is_active = True
                driver.disponibilite = True
                message = "Livreur activé avec succès"
                
            elif action == "suspend":
                user.statut = "suspendu"
                user.is_active = False
                driver.disponibilite = False
                message = "Livreur suspendu avec succès"
                
            elif action == "delete":
                # Soft delete
                user.statut = "suspendu"
                user.is_active = False
                driver.disponibilite = False
                # Modifier l'email pour éviter les conflits
                import time
                timestamp = int(time.time())
                original_email = user.email
                user.email = f"deleted_{timestamp}_{original_email}"
                message = "Livreur supprimé avec succès"
                logger.info(f"Livreur soft-delete: {original_email} -> {user.email}")
                
            else:
                return None, "Action non valide"
            
            # Mettre à jour les dates
            user.updated_at = datetime.utcnow()
            driver.updated_at = datetime.utcnow()
            
            db.commit()
            db.refresh(user)
            
            logger.info(f"Statut livreur changé: {user.email} -> {action}")
            return user, message
            
        except Exception as e:
            db.rollback()
            logger.error(f"Erreur changement statut livreur: {e}")
            return None, f"Erreur: {str(e)}"
    
    @staticmethod
    async def get_seller_drivers(
        db: Session,
        seller_id: UUID,
        statut: Optional[str] = None,
        disponibilite: Optional[bool] = None,
        zone: Optional[str] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[Driver]:
        """
        Récupère la liste des livreurs d'un vendeur avec filtres
        """
        try:
            # Construire la requête de base
            query = db.query(Driver).filter(Driver.seller_id == seller_id)
            
            # Filtrer par disponibilité
            if disponibilite is not None:
                query = query.filter(Driver.disponibilite == disponibilite)
            
            # Filtrer par zone
            if zone:
                query = query.filter(Driver.zone_livraison.ilike(f"%{zone}%"))
            
            # Joindre avec User pour les autres filtres
            query = query.join(User, User.id == Driver.user_id)
            
            # Filtrer par statut
            if statut:
                query = query.filter(User.statut == statut)
            
            # Charger les données utilisateur
            query = query.options(joinedload(Driver.user))
            
            # Trier par date de création (plus récent d'abord)
            query = query.order_by(Driver.created_at.desc())
            
            # Appliquer pagination
            drivers = query.offset(skip).limit(limit).all()
            
            logger.debug(f"Récupération de {len(drivers)} livreurs pour le vendeur {seller_id}")
            return drivers
            
        except Exception as e:
            logger.error(f"Erreur récupération livreurs: {e}")
            return []
    
    @staticmethod
    async def get_driver_details(
        db: Session,
        driver_id: UUID,
        seller_id: UUID
    ) -> Optional[Driver]:
        """
        Récupère les détails d'un livreur spécifique
        """
        try:
            driver = db.query(Driver).filter(
                and_(
                    Driver.id == driver_id,
                    Driver.seller_id == seller_id
                )
            ).options(joinedload(Driver.user)).first()
            
            if driver:
                logger.debug(f"Détails livreur récupérés: {driver_id}")
            else:
                logger.warning(f"Livreur non trouvé: {driver_id} pour vendeur {seller_id}")
            
            return driver
            
        except Exception as e:
            logger.error(f"Erreur récupération détails livreur: {e}")
            return None
    
    @staticmethod
    async def get_driver_stats(
        db: Session,
        seller_id: UUID
    ) -> Dict[str, Any]:
        """
        Récupère les statistiques des livreurs d'un vendeur
        """
        try:
            # Compter les livreurs par statut
            statut_stats = db.query(
                User.statut,
                func.count(Driver.id).label("count")
            ).join(Driver, Driver.user_id == User.id)\
             .filter(Driver.seller_id == seller_id)\
             .group_by(User.statut).all()
            
            # Compter les livreurs par disponibilité
            disponibilite_stats = db.query(
                Driver.disponibilite,
                func.count(Driver.id).label("count")
            ).filter(Driver.seller_id == seller_id)\
             .group_by(Driver.disponibilite).all()
            
            # Total des livreurs
            total_drivers = db.query(func.count(Driver.id))\
                             .filter(Driver.seller_id == seller_id)\
                             .scalar() or 0
            
            # Livreurs actifs (statut = actif ET is_active = True)
            active_drivers = db.query(func.count(Driver.id))\
                              .join(User, User.id == Driver.user_id)\
                              .filter(
                                  Driver.seller_id == seller_id,
                                  User.statut == "actif",
                                  User.is_active == True
                              ).scalar() or 0
            
            # Formater les résultats
            statut_dict = {statut: count for statut, count in statut_stats}
            disponibilite_dict = {
                "disponible": 0,
                "indisponible": 0
            }
            
            for disponibilite, count in disponibilite_stats:
                if disponibilite:
                    disponibilite_dict["disponible"] = count
                else:
                    disponibilite_dict["indisponible"] = count
            
            logger.debug(f"Statistiques récupérées pour vendeur {seller_id}")
            
            return {
                "total": total_drivers,
                "active": active_drivers,
                "by_statut": statut_dict,
                "by_disponibilite": disponibilite_dict
            }
            
        except Exception as e:
            logger.error(f"Erreur récupération statistiques: {e}")
            return {
                "total": 0,
                "active": 0,
                "by_statut": {},
                "by_disponibilite": {"disponible": 0, "indisponible": 0}
            }
    
    @staticmethod
    async def search_drivers(
        db: Session,
        seller_id: UUID,
        search_term: str,
        skip: int = 0,
        limit: int = 50
    ) -> List[Driver]:
        """
        Recherche des livreurs par nom, email ou téléphone
        """
        try:
            query = db.query(Driver).join(User, User.id == Driver.user_id)\
                .filter(
                    and_(
                        Driver.seller_id == seller_id,
                        or_(
                            User.full_name.ilike(f"%{search_term}%"),
                            User.email.ilike(f"%{search_term}%"),
                            User.telephone.ilike(f"%{search_term}%"),
                            Driver.zone_livraison.ilike(f"%{search_term}%")
                        )
                    )
                ).options(joinedload(Driver.user))
            
            drivers = query.order_by(Driver.created_at.desc())\
                          .offset(skip).limit(limit).all()
            
            logger.debug(f"Recherche '{search_term}': {len(drivers)} résultats")
            return drivers
            
        except Exception as e:
            logger.error(f"Erreur recherche livreurs: {e}")
            return []
    
    @staticmethod
    async def get_available_zones(
        db: Session,
        seller_id: UUID
    ) -> List[Dict[str, Any]]:
        """
        Récupère les zones de livraison disponibles avec statistiques
        """
        try:
            from sqlalchemy import distinct
            
            # Récupérer les zones distinctes avec compteurs
            zones_stats = db.query(
                Driver.zone_livraison,
                func.count(Driver.id).label("total"),
                func.sum(func.cast(Driver.disponibilite, func.Integer)).label("disponibles")
            ).filter(
                Driver.seller_id == seller_id,
                Driver.zone_livraison.isnot(None),
                Driver.zone_livraison != ""
            ).group_by(Driver.zone_livraison)\
             .order_by(func.count(Driver.id).desc()).all()
            
            result = []
            for zone, total, disponibles in zones_stats:
                result.append({
                    "zone": zone,
                    "total": total,
                    "disponibles": disponibles or 0,
                    "indisponibles": total - (disponibles or 0)
                })
            
            logger.debug(f"Zones récupérées pour vendeur {seller_id}: {len(result)} zones")
            return result
            
        except Exception as e:
            logger.error(f"Erreur récupération zones: {e}")
            return []
    
    @staticmethod
    async def get_driver_by_user_id(
        db: Session,
        user_id: UUID,
        seller_id: UUID
    ) -> Optional[Driver]:
        """
        Récupère un livreur par son user_id
        """
        try:
            driver = db.query(Driver).filter(
                and_(
                    Driver.user_id == user_id,
                    Driver.seller_id == seller_id
                )
            ).options(joinedload(Driver.user)).first()
            
            return driver
            
        except Exception as e:
            logger.error(f"Erreur récupération livreur par user_id: {e}")
            return None
    
    @staticmethod
    async def update_driver_zone(
        db: Session,
        driver_id: UUID,
        seller_id: UUID,
        new_address: str
    ) -> tuple[Optional[Driver], str]:
        """
        Met à jour la zone de livraison d'un livreur basée sur une nouvelle adresse
        """
        try:
            driver = db.query(Driver).filter(
                and_(
                    Driver.id == driver_id,
                    Driver.seller_id == seller_id
                )
            ).first()
            
            if not driver:
                return None, "Livreur non trouvé"
            
            # Mettre à jour l'adresse de l'utilisateur
            user = db.query(User).filter(User.id == driver.user_id).first()
            if user:
                user.adresse = new_address
                user.updated_at = datetime.utcnow()
            
            # Mettre à jour la zone de livraison avec géocodage
            try:
                new_zone = geocoding_service.extract_zone_from_address(new_address)
                driver.zone_livraison = new_zone
                logger.info(f"Zone mise à jour pour livreur {driver_id}: {new_zone}")
            except Exception as e:
                logger.error(f"Erreur géocodage pour mise à jour zone: {e}")
                # Garder l'ancienne zone en cas d'erreur
            
            driver.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(driver)
            
            return driver, "Zone de livraison mise à jour avec succès"
            
        except Exception as e:
            db.rollback()
            logger.error(f"Erreur mise à jour zone livreur: {e}")
            return None, f"Erreur mise à jour zone: {str(e)}"
    
    @staticmethod
    async def bulk_update_disponibilite(
        db: Session,
        seller_id: UUID,
        driver_ids: List[UUID],
        disponibilite: bool
    ) -> tuple[int, str]:
        """
        Met à jour la disponibilité de plusieurs livreurs en masse
        """
        try:
            result = db.query(Driver).filter(
                and_(
                    Driver.seller_id == seller_id,
                    Driver.id.in_(driver_ids)
                )
            ).update(
                {Driver.disponibilite: disponibilite, Driver.updated_at: datetime.utcnow()},
                synchronize_session=False
            )
            
            db.commit()
            
            logger.info(f"Disponibilité mise à jour pour {result} livreurs: {disponibilite}")
            return result, f"Disponibilité mise à jour pour {result} livreur(s)"
            
        except Exception as e:
            db.rollback()
            logger.error(f"Erreur mise à jour disponibilité en masse: {e}")
            return 0, f"Erreur mise à jour: {str(e)}"
    
    @staticmethod
    async def get_drivers_with_pending_status(
        db: Session,
        seller_id: UUID
    ) -> List[Driver]:
        """
        Récupère les livreurs avec statut 'en_attente' qui nécessitent une validation
        """
        try:
            drivers = db.query(Driver).join(User, User.id == Driver.user_id)\
                .filter(
                    and_(
                        Driver.seller_id == seller_id,
                        User.statut == "en_attente"
                    )
                ).options(joinedload(Driver.user))\
                .order_by(User.created_at.asc()).all()
            
            return drivers
            
        except Exception as e:
            logger.error(f"Erreur récupération livreurs en attente: {e}")
            return []

# Import pour la recherche
from sqlalchemy import or_

# Export de la classe
__all__ = ["DriverService"]