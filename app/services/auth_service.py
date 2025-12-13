from datetime import datetime
from sqlite3 import IntegrityError
import uuid
from requests import Session

from app.core.security import hash_password
from app.models.seller import Seller
from app.models.user import User


def create_user(
    db: Session, 
    nom_complet: str, 
    email: str, 
    password: str, 
    role: str,
    telephone: str,
    company_name: str = None,
    adresse: str = None
):
    try:
        # Vérifier si l'email existe déjà
        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            raise ValueError("Un utilisateur avec cet email existe déjà")

        # Générer un UUID pour l'utilisateur
        user_id = uuid.uuid4()  # ✅ CORRECTION : Retirer str()
        password_hash = hash_password(password)
        now = datetime.now()
        
        # ✅ CORRECTION : Utiliser "Vendeur" avec V majuscule
        user_role = "Vendeur" if role.lower() in ["vendeur", "seller"] else role
        
        # Créer l'utilisateur
        user = User(
            id=user_id,
            full_name=nom_complet,
            email=email,
            telephone=telephone,
            role=user_role,  # ✅ CORRIGÉ : "Vendeur" avec V majuscule
            adresse=adresse,
            password_hash=password_hash,
            created_at=now,
            updated_at=now
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        # ✅ CORRECTION : Vérifier avec le rôle corrigé
        if user_role == "Vendeur":
            # Validation du company_name pour les vendeurs
            if not company_name or company_name.strip() == "":
                company_name = f"Boutique de {nom_complet.split()[0]}"  # Premier nom
            
            seller = Seller(
                id=uuid.uuid4(),  # ✅ CORRECTION : Nouvel UUID pour Seller
                user_id=user_id,  # ✅ CORRECTION : Référence à l'user
                company_name=company_name.strip(),
                created_at=now,
                updated_at=now
            )
            db.add(seller)
            db.commit()
            db.refresh(seller)

        return user

    except IntegrityError as e:
        db.rollback()
        raise ValueError(f"Erreur d'intégrité de la base de données: {str(e)}")
    except Exception as e:
        db.rollback()
        raise ValueError(f"Erreur lors de la création de l'utilisateur: {str(e)}")