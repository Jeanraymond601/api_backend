from datetime import datetime, timedelta
import os
import uuid
import random
import secrets
from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.db import get_db
from app.models.seller import Seller
from app.models.user import User
from app.models.password_reset_code import PasswordResetCode
from app.schemas.user import UserResponse
from app.schemas.auth_schema import RegisterSchema, LoginSchema, ForgotPasswordSchema, VerifyResetCodeSchema, ResetPasswordSchema
from app.services.email_service import email_service
from app.core.security import SecurityManager

router = APIRouter(prefix="/auth", tags=["auth"])
security_manager = SecurityManager()

# ================================
# UTILITAIRES
# ================================
def normalize_role(role: str) -> str:
    """Normalise le rôle utilisateur"""
    role_lower = role.lower().strip()
    
    role_mapping = {
        "vendeur": "Vendeur",
        "seller": "Vendeur", 
        "livreur": "Livreur",
        "driver": "Livreur",
        "delivery": "Livreur",
        "admin": "Admin",
        "administrator": "Admin"
    }
    
    return role_mapping.get(role_lower, "Client")

def create_user_response(user_data: dict, seller_info: dict = None) -> dict:
    """Version simplifiée et robuste"""
    
    # Base response
    response = {
        "user_id": str(user_data.get("id", "")),
        "email": user_data.get("email", ""),
        "role": (user_data.get("role", "") or "").upper(),
        "full_name": user_data.get("full_name", "") or "",
        "telephone": user_data.get("telephone", "") or "",
        "adresse": user_data.get("adresse", "") or "",
        "is_active": bool(user_data.get("is_active", True))
    }
    
    # Ajouter seller_info si disponible
    if seller_info and isinstance(seller_info, dict):
        # Récupérer seller_id (peut être sous différentes clés)
        seller_id = seller_info.get("seller_id") or seller_info.get("id")
        if seller_id:
            response["seller_id"] = str(seller_id)
        
        # Ajouter d'autres champs intéressants
        for key in ["company_name", "abonnement_status"]:
            if key in seller_info:
                response[key] = seller_info[key]
    
    return response

# ================================
# ENDPOINTS D'AUTHENTIFICATION
# ================================
@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(user_data: RegisterSchema, db: Session = Depends(get_db)):
    """
    Endpoint d'inscription utilisateur
    """
    try:
        print(f"📧 Tentative d'inscription: {user_data.email}")
        
        # Vérifier si l'utilisateur existe déjà
        existing_user = db.query(User).filter(User.email == user_data.email).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Un utilisateur avec cet email existe déjà"
            )

        # Préparer les données utilisateur
        user_id = uuid.uuid4()
        now = datetime.now()
        normalized_role = normalize_role(user_data.role)
        
        # Créer l'utilisateur
        new_user = User(
            id=user_id,
            email=user_data.email,
            full_name=user_data.full_name,
            telephone=user_data.phone or "",
            role=normalized_role,
            adresse=user_data.adresse or "",
            password=security_manager.hash_password(user_data.password),
            created_at=now,
            updated_at=now,
            is_active=True
        )
        db.add(new_user)
    
        # Créer le seller si rôle vendeur
        if normalized_role == "Vendeur":
            company_name = user_data.company_name or f"Boutique de {user_data.full_name.split()[0] if user_data.full_name else 'Anonyme'}"
            
            new_seller = Seller(
                id=uuid.uuid4(),
                user_id=user_id,
                company_name=company_name,
                date_debut_abonnement=now.date(),
                date_fin_abonnement=now.date() + timedelta(days=30),  # Abonnement 30 jours par défaut
                created_at=now,
                updated_at=now
            )
            db.add(new_seller)
    
        db.commit()
        db.refresh(new_user)
        
        print(f"✅ Utilisateur créé avec succès: {new_user.email} (Rôle: {new_user.role})")
        return new_user
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"❌ Erreur lors de l'inscription: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la création de l'utilisateur"
        )

@router.post("/login")
def login_user(login_data: LoginSchema, db: Session = Depends(get_db)):
    """
    Endpoint de connexion utilisateur - VERSION AVEC seller_id DANS LE TOKEN
    """
    try:
        print(f"🔐 Tentative de connexion: {login_data.email}")
        
        # Rechercher l'utilisateur avec SQL direct pour éviter les problèmes de relations
        user_query = text("""
            SELECT 
                id, email, full_name, telephone, role, adresse, 
                password, is_active, created_at, updated_at
            FROM users 
            WHERE email = :email
        """)
        
        result = db.execute(user_query, {"email": login_data.email})
        user_row = result.fetchone()
        
        if not user_row:
            print(f"❌ Utilisateur non trouvé: {login_data.email}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email ou mot de passe incorrect"
            )
        
        # Convertir le résultat en dict
        user_dict = {
            'id': user_row[0],
            'email': user_row[1],
            'full_name': user_row[2],
            'telephone': user_row[3],
            'role': user_row[4],
            'adresse': user_row[5],
            'password': user_row[6],
            'is_active': user_row[7],
            'created_at': user_row[8],
            'updated_at': user_row[9]
        }
        
        # Vérifier le mot de passe
        if not security_manager.verify_password(login_data.password, user_dict['password']):
            print(f"❌ Mot de passe incorrect pour: {login_data.email}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email ou mot de passe incorrect"
            )
        
        # Vérifier si le compte est actif
        if not user_dict['is_active']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Compte désactivé"
            )
        
        # ========== RECHERCHER seller_id ==========
        seller_info = None
        seller_id = None
        
        # Vérifier d'abord si l'utilisateur est un vendeur
        if user_dict['role'].lower() in ["vendeur", "seller", "vendor"]:
            seller_query = text("""
                SELECT id, company_name, abonnement_status
                FROM sellers 
                WHERE user_id = :user_id
            """)
            seller_result = db.execute(seller_query, {"user_id": user_dict['id']})
            seller_row = seller_result.fetchone()
            
            if seller_row:
                seller_id = str(seller_row[0])
                seller_info = {
                    "seller_id": seller_id,
                    "company_name": seller_row[1],
                    "abonnement_status": seller_row[2]
                }
                print(f"✅ Seller trouvé: ID = {seller_id}")
            else:
                print(f"⚠️  Aucun seller trouvé pour user_id: {user_dict['id']}")
        
        # ========== CORRECTION: CRÉER LE TOKEN AVEC seller_id ==========
        # Utilisez la NOUVELLE méthode create_jwt_token qui accepte seller_id
        from app.core.security import create_seller_token, create_access_token
        
        user_id_str = str(user_dict['id'])
        
        if seller_id:
            # ⭐ Créer le token AVEC seller_id inclus dans le payload JWT
            print(f"✅ Création token AVEC seller_id: {seller_id}")
            token = create_seller_token(
                user_id=user_id_str,
                email=user_dict['email'],
                role=user_dict['role'].upper(),
                full_name=user_dict['full_name'] or "",
                seller_id=seller_id
            )
        else:
            # Créer le token sans seller_id
            print(f"✅ Création token SANS seller_id (utilisateur normal)")
            token = create_access_token({
                "user_id": user_id_str,
                "email": user_dict['email'],
                "role": user_dict['role'].upper(),
                "full_name": user_dict['full_name'] or ""
            })
        
        # Vérifier ce qu'il y a dans le token (pour debug)
        try:
            payload = security_manager.verify_jwt_token(token)
            print(f"📋 Token payload vérifié:")
            print(f"   - user_id: {payload.get('user_id')}")
            print(f"   - seller_id dans token: {payload.get('seller_id', 'NON PRÉSENT')}")
        except:
            print("⚠️  Impossible de décoder le token pour vérification")
        
        # Mettre à jour la date de dernière connexion
        update_query = text("""
            UPDATE users 
            SET updated_at = :now 
            WHERE id = :user_id
        """)
        db.execute(update_query, {
            "now": datetime.now(),
            "user_id": user_dict['id']
        })
        db.commit()
        
        # Préparer la réponse
        response_data = {
            "access_token": token,
            "token_type": "bearer",
            **create_user_response(user_dict, seller_info)
        }
        
        print(f"✅ Connexion réussie: {user_dict['email']}")
        print(f"   Rôle: {user_dict['role'].upper()}")
        print(f"   Token contient seller_id: {'✓' if seller_id else '✗'}")
        
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Erreur lors de la connexion: {str(e)}")
        import traceback
        traceback.print_exc()  # Pour debug
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur technique lors de l'authentification"
        )

# ================================
# GESTION MOT DE PASSE
# ================================
@router.post("/forgot-password")
async def forgot_password(forgot_data: ForgotPasswordSchema, db: Session = Depends(get_db)):
    """
    Endpoint pour demander une réinitialisation de mot de passe - Version Production
    """
    try:
        # 1. Rechercher l'utilisateur
        user = db.query(User).filter(User.email == forgot_data.email).first()
        
        if not user:
            return {"message": "Si l'email existe, un code de réinitialisation a été envoyé"}
        
        # 2. Générer un code
        reset_code = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        expires_at = datetime.now() + timedelta(minutes=15)
        
        # 3. Supprimer les anciens codes
        try:
            db.query(PasswordResetCode).filter(
                PasswordResetCode.user_id == user.id
            ).delete()
        except:
            pass  # Ignorer les erreurs de suppression
        
        # 4. Créer le nouveau code
        new_reset_code = PasswordResetCode(
            id=uuid.uuid4(),
            user_id=user.id,
            email=user.email,
            code=reset_code,
            expires_at=expires_at,
            verified=False,
            attempts=0
        )
        
        try:
            db.add(new_reset_code)
            db.commit()
        except Exception as db_error:
            db.rollback()
            # Log l'erreur mais continuer pour l'email
            print(f"Database error: {db_error}")
        
        # 5. Envoyer l'email (silencieusement)
        try:
            email_service.send_reset_code_email(user.email, reset_code)
        except Exception as email_error:
            # Log l'erreur mais ne pas l'exposer à l'utilisateur
            print(f"Email error: {email_error}")
        
        # 6. Toujours retourner le même message
        return {"message": "Si l'email existe, un code de réinitialisation a été envoyé"}
        
    except Exception:
        # En production, on log mais on retourne toujours le même message
        import traceback
        traceback.print_exc()
        
        return {"message": "Si l'email existe, un code de réinitialisation a été envoyé"}

@router.post("/verify-reset-code")
async def verify_reset_code(verification_data: VerifyResetCodeSchema, db: Session = Depends(get_db)):
    """
    Endpoint pour vérifier un code de réinitialisation
    """
    try:
        print(f"🔍 Vérification code pour: {verification_data.email}")
        
        user = db.query(User).filter(User.email == verification_data.email).first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Utilisateur non trouvé"
            )
        
        # Vérifier le code - CORRIGÉ
        reset_code_obj = db.query(PasswordResetCode).filter(
            PasswordResetCode.user_id == user.id,
            PasswordResetCode.email == user.email,
            PasswordResetCode.code == verification_data.code,
            PasswordResetCode.verified == False,
            PasswordResetCode.used_at == None,  # CORRECTION: "used_at" est null, pas "used == False"
            PasswordResetCode.expires_at > datetime.now(),
            PasswordResetCode.attempts < 3
        ).first()
        
        if not reset_code_obj:
            # Incrémenter les tentatives si le code existe mais est invalide
            existing_code = db.query(PasswordResetCode).filter(
                PasswordResetCode.user_id == user.id,
                PasswordResetCode.email == user.email,
                PasswordResetCode.used_at == None  # CORRECTION: vérifier "used_at" null
            ).first()
            
            if existing_code:
                existing_code.attempts += 1
                db.commit()
            
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Code invalide, expiré ou trop de tentatives"
            )
        
        # Marquer le code comme vérifié
        reset_code_obj.verified = True
        
        # Générer un token de reset sécurisé
        reset_token = secrets.token_urlsafe(32)
        reset_code_obj.reset_token = reset_token
        
        db.commit()
        
        return {
            "message": "Code vérifié avec succès",
            "reset_token": reset_token
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"❌ Erreur verify-reset-code: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la vérification du code"
        )

@router.post("/reset-password")
async def reset_password(reset_data: ResetPasswordSchema, db: Session = Depends(get_db)):
    """
    Endpoint pour réinitialiser le mot de passe
    """
    try:
        print(f"🔄 Reset password pour: {reset_data.email}")
        
        user = db.query(User).filter(User.email == reset_data.email).first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Utilisateur non trouvé"
            )
        
        # Vérifier le token de reset - CORRIGÉ
        reset_code_obj = db.query(PasswordResetCode).filter(
            PasswordResetCode.user_id == user.id,
            PasswordResetCode.email == user.email,
            PasswordResetCode.reset_token == reset_data.reset_token,
            PasswordResetCode.verified == True,
            PasswordResetCode.used_at == None,  # CORRECTION: "used_at" est null, pas "used == False"
            PasswordResetCode.expires_at > datetime.now()
        ).first()
        
        if not reset_code_obj:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Token de réinitialisation invalide ou expiré"
            )
        
        # Mettre à jour le mot de passe
        user.password = security_manager.hash_password(reset_data.new_password)
        user.updated_at = datetime.now()
        
        # Marquer le code comme utilisé - CORRIGÉ
        reset_code_obj.used_at = datetime.now()  # CORRECTION: set "used_at", pas "used = True"
        
        db.commit()
        
        print(f"✅ Mot de passe réinitialisé pour: {user.email}")
        
        return {
            "message": "Mot de passe réinitialisé avec succès"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"❌ Erreur reset-password: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la réinitialisation"
        )

# ================================
# UTILITAIRES
# ================================
@router.get("/check-email/{email}")
def check_email_availability(email: str, db: Session = Depends(get_db)):
    """
    Vérifie la disponibilité d'un email
    """
    try:
        user = db.query(User).filter(User.email == email).first()
        
        return {
            "available": user is None,
            "email": email
        }
        
    except Exception as e:
        print(f"❌ Erreur check-email: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la vérification de l'email"
        )

@router.get("/test-jointure/{user_id}")
def test_jointure(user_id: uuid.UUID, db: Session = Depends(get_db)):
    """
    Teste les jointures entre User et Seller
    """
    try:
        # Utiliser SQL direct pour éviter les problèmes de relations
        query = text("""
            SELECT 
                u.id as user_id, u.email, u.role, u.full_name,
                s.id as seller_id, s.company_name
            FROM users u
            LEFT JOIN sellers s ON u.id = s.user_id
            WHERE u.id = :user_id
        """)
        
        result = db.execute(query, {"user_id": user_id})
        row = result.fetchone()
        
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Utilisateur non trouvé"
            )
        
        response = {
            "user_id": str(row[0]),
            "email": row[1],
            "role": row[2],
            "full_name": row[3],
            "has_seller": row[4] is not None
        }
        
        if row[4]:  # seller_id
            response["seller"] = {
                "seller_id": str(row[4]),
                "company_name": row[5]
            }
        
        return response
        
    except Exception as e:
        print(f"❌ Erreur test-jointure: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors du test de jointure"
        )

@router.get("/health")
def health_check():
    """
    Endpoint de santé de l'API auth
    """
    return {
        "status": "healthy",
        "service": "auth",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0",
        "security": security_manager is not None
    }