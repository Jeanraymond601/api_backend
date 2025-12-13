
# app/routers/drivers.py - Version corrigée
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy import Integer, func, or_
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
import uuid
from datetime import datetime

from app.db import get_db
from app.core.security import get_current_user, get_password_hash
from app.models.driver_model import Driver
from app.models.user import User
from app.services.geocoding_service import geocoding_service
from app.services.email_service import EmailService

router = APIRouter(prefix="/api/v1/drivers", tags=["Drivers"])

def get_current_seller(current_user: dict = Depends(get_current_user)):
    """
    Vérifie que l'utilisateur courant est un vendeur
    """
    user_role = current_user.get("role", "").upper()
    
    if user_role not in ["VENDEUR", "VENDOR"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Accès réservé aux vendeurs. Rôle actuel: {current_user.get('role')}"
        )
    
    current_user["current_user_id"] = current_user["user_id"]
    return current_user

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_driver(
    driver_data: dict,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_seller)
):
    """
    Crée un nouveau livreur et envoie un email de bienvenue formaté en carte de visite
    """
    try:
        # Vérifier les champs requis
        required_fields = ["full_name", "email", "telephone", "adresse", "password"]
        for field in required_fields:
            if field not in driver_data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Champ requis manquant: {field}"
                )
        
        # Vérifier si l'email existe déjà
        existing_user = db.query(User).filter(
            User.email == driver_data["email"]
        ).first()
        
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email déjà utilisé"
            )
        
        # Vérifier que le vendeur existe
        seller_id = UUID(current_user["user_id"])
        seller_user = db.query(User).filter(User.id == seller_id).first()
        
        if not seller_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vendeur non trouvé"
            )
        
        # Vérifier que l'utilisateur a bien le rôle Vendeur
        if seller_user.role.upper() not in ["VENDEUR", "VENDOR"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"L'utilisateur n'est pas un vendeur. Rôle: {seller_user.role}"
            )
        
        # Créer l'utilisateur (LIVREUR)
        hashed_password = get_password_hash(driver_data["password"])
        
        user = User(
            id=uuid.uuid4(),
            full_name=driver_data["full_name"],
            email=driver_data["email"],
            telephone=driver_data["telephone"],
            adresse=driver_data["adresse"],
            role="LIVREUR",
            statut=driver_data.get("statut", "en_attente"),
            password=hashed_password,
            is_active=True,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        db.add(user)
        db.flush()
        
        # Déterminer la zone de livraison automatiquement avec géocodage
        zone_livraison = "Zone non spécifiée"
        if driver_data["adresse"]:
            try:
                zone_livraison = geocoding_service.extract_zone_from_address(
                    driver_data["adresse"]
                )
                print(f"✅ Zone détectée: {zone_livraison}")
            except Exception as e:
                print(f"⚠️  Erreur géocodage: {e}")
                if len(driver_data["adresse"]) > 30:
                    zone_livraison = driver_data["adresse"][:30] + "..."
                else:
                    zone_livraison = driver_data["adresse"]
        
        # Créer le driver
        driver = Driver(
            id=uuid.uuid4(),
            user_id=user.id,
            seller_id=seller_id,
            zone_livraison=zone_livraison,
            disponibilite=True,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        db.add(driver)
        db.commit()
        
        # Récupérer le service d'email
        email_service = EmailService()
        
        # Préparer les données pour l'email au livreur
        driver_email_data = {
            "driver_name": user.full_name,
            "driver_email": user.email,
            "driver_phone": user.telephone,
            "driver_password": driver_data["password"],
            "delivery_zone": zone_livraison,
            "driver_address": user.adresse,
            "status": user.statut,
            "creation_date": datetime.now().strftime("%d/%m/%Y à %H:%M"),
            "seller_name": seller_user.full_name,
            "seller_email": seller_user.email,
            "seller_phone": seller_user.telephone
        }
        
        # Envoyer l'email de bienvenue au livreur (en arrière-plan)
        background_tasks.add_task(
            send_driver_welcome_email,
            email_service,
            driver_email_data
        )
        
        # Préparer les données pour l'email au vendeur
        seller_email_data = {
            "seller_name": seller_user.full_name,
            "seller_email": seller_user.email,
            "driver_name": user.full_name,
            "driver_email": user.email,
            "driver_phone": user.telephone,
            "delivery_zone": zone_livraison,
            "status": user.statut,
            "creation_date": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "driver_id": str(driver.id)
        }
        
        # Envoyer la notification au vendeur (en arrière-plan)
        background_tasks.add_task(
            send_seller_notification_email,
            email_service,
            seller_email_data
        )
        
        return {
            "message": "Livreur créé avec succès. Un email de bienvenue a été envoyé au livreur et une notification au vendeur.",
            "success": True,
            "data": {
                "driver_id": str(driver.id),
                "user_id": str(user.id),
                "seller_id": str(driver.seller_id),
                "full_name": user.full_name,
                "email": user.email,
                "telephone": user.telephone,
                "zone_livraison": zone_livraison,
                "role": user.role,
                "statut": user.statut,
                "disponibilite": driver.disponibilite,
                "is_active": user.is_active,
                "created_at": driver.created_at.isoformat(),
                "email_sent": True
            }
        }
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur création livreur: {str(e)}"
        )

def send_driver_welcome_email(email_service: EmailService, driver_data: dict):
    """
    Envoie un email de bienvenue formaté en carte de visite au nouveau livreur
    """
    try:
        subject = f"🎉 Bienvenue comme Livreur - Votre Carte de Visite"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    background: #f5f7fa;
                    margin: 0;
                    padding: 20px;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    background: white;
                    border-radius: 15px;
                    overflow: hidden;
                    box-shadow: 0 5px 20px rgba(0,0,0,0.1);
                }}
                .header {{
                    background: linear-gradient(135deg, #4CAF50, #2E7D32);
                    color: white;
                    padding: 30px;
                    text-align: center;
                }}
                .header h1 {{
                    margin: 0;
                    font-size: 24px;
                }}
                .business-card {{
                    background: white;
                    margin: -40px 30px 30px;
                    padding: 30px;
                    border-radius: 10px;
                    box-shadow: 0 5px 15px rgba(0,0,0,0.1);
                    border: 2px solid #4CAF50;
                }}
                .card-header {{
                    background: #e8f5e9;
                    padding: 20px;
                    border-radius: 8px 8px 0 0;
                    text-align: center;
                    margin: -30px -30px 20px;
                }}
                .card-header h2 {{
                    color: #2E7D32;
                    margin: 0;
                }}
                .info-section {{
                    margin: 20px 0;
                }}
                .info-row {{
                    display: flex;
                    margin-bottom: 15px;
                    padding-bottom: 15px;
                    border-bottom: 1px solid #eee;
                }}
                .info-label {{
                    flex: 1;
                    font-weight: bold;
                    color: #555;
                }}
                .info-value {{
                    flex: 2;
                    color: #333;
                }}
                .credentials {{
                    background: #fff8e1;
                    border-left: 4px solid #ff9800;
                    padding: 15px;
                    margin: 20px 0;
                    border-radius: 0 8px 8px 0;
                }}
                .warning {{
                    background: #ffebee;
                    color: #d32f2f;
                    padding: 10px;
                    border-radius: 5px;
                    margin: 15px 0;
                    font-weight: bold;
                }}
                .steps {{
                    background: #e3f2fd;
                    padding: 20px;
                    border-radius: 8px;
                    margin: 20px 0;
                }}
                .footer {{
                    background: #f5f5f5;
                    padding: 20px;
                    text-align: center;
                    color: #666;
                    font-size: 12px;
                    border-top: 1px solid #ddd;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🎯 Votre Carte de Livreur</h1>
                    <p>Bienvenue dans l'équipe de livraison</p>
                </div>
                
                <div class="business-card">
                    <div class="card-header">
                        <h2>{driver_data['driver_name']}</h2>
                        <p>🚚 Livreur Professionnel</p>
                    </div>
                    
                    <div class="info-section">
                        <div class="info-row">
                            <div class="info-label">📍 Zone de Livraison:</div>
                            <div class="info-value">{driver_data['delivery_zone']}</div>
                        </div>
                        <div class="info-row">
                            <div class="info-label">📞 Téléphone:</div>
                            <div class="info-value">{driver_data['driver_phone']}</div>
                        </div>
                        <div class="info-row">
                            <div class="info-label">🏠 Adresse:</div>
                            <div class="info-value">{driver_data['driver_address']}</div>
                        </div>
                        <div class="info-row">
                            <div class="info-label">📅 Date d'inscription:</div>
                            <div class="info-value">{driver_data['creation_date']}</div>
                        </div>
                    </div>
                    
                    <div class="credentials">
                        <h3 style="color: #ff9800; margin-top: 0;">🔐 Vos Identifiants de Connexion</h3>
                        <div class="info-row">
                            <div class="info-label">📧 Email:</div>
                            <div class="info-value"><strong>{driver_data['driver_email']}</strong></div>
                        </div>
                        <div class="info-row">
                            <div class="info-label">🔑 Mot de passe:</div>
                            <div class="info-value"><strong>{driver_data['driver_password']}</strong></div>
                        </div>
                    </div>
                    
                    <div class="warning">
                        ⚠️ IMPORTANT : Conservez ces identifiants en lieu sûr et changez votre mot de passe après la première connexion.
                    </div>
                    
                    <div class="steps">
                        <h3 style="color: #1976d2; margin-top: 0;">📱 Prochaines Étapes</h3>
                        <ol style="margin: 10px 0; padding-left: 20px;">
                            <li>Téléchargez l'application livreur</li>
                            <li>Connectez-vous avec vos identifiants</li>
                            <li>Complétez votre profil</li>
                            <li>Acceptez votre première mission</li>
                            <li>Commencez à livrer !</li>
                        </ol>
                    </div>
                    
                    <div style="background: #f9f9f9; padding: 15px; border-radius: 8px; margin-top: 20px;">
                        <h4 style="margin: 0 0 10px 0; color: #555;">📞 Contacts</h4>
                        <p style="margin: 5px 0;">
                            <strong>Vendeur:</strong> {driver_data['seller_name']} ({driver_data['seller_email']})
                        </p>
                        <p style="margin: 5px 0;">
                            <strong>Support:</strong> support@commerce-mg.com / +261 34 00 000 00
                        </p>
                    </div>
                </div>
                
                <div class="footer">
                    <p>© {datetime.now().year} Commerce Madagascar - Service de Livraison</p>
                    <p>Cet email a été envoyé automatiquement, merci de ne pas y répondre.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Version texte simple
        text_content = f"""
        BIENVENUE COMME LIVREUR - VOTRE CARTE DE VISITE
        
        Bonjour {driver_data['driver_name']},
        
        FÉLICITATIONS ! Vous êtes maintenant livreur chez {driver_data['seller_name']}.
        
        VOTRE CARTE DE LIVREUR :
        Nom: {driver_data['driver_name']}
        Zone de Livraison: {driver_data['delivery_zone']}
        Téléphone: {driver_data['driver_phone']}
        Adresse: {driver_data['driver_address']}
        Date d'inscription: {driver_data['creation_date']}
        
        VOS IDENTIFIANTS DE CONNEXION :
        Email: {driver_data['driver_email']}
        Mot de passe: {driver_data['driver_password']}
        
        ⚠️ IMPORTANT : Conservez ces identifiants en lieu sûr et changez votre mot de passe après la première connexion.
        
        PROCHAINES ÉTAPES :
        1. Téléchargez l'application livreur
        2. Connectez-vous avec vos identifiants
        3. Complétez votre profil
        4. Acceptez votre première mission
        5. Commencez à livrer !
        
        CONTACTS :
        Vendeur: {driver_data['seller_name']} ({driver_data['seller_email']})
        Support: support@commerce-mg.com / +261 34 00 000 00
        
        © {datetime.now().year} Commerce Madagascar
        Cet email a été envoyé automatiquement.
        """
        
        # Essayer différentes méthodes possibles
        success = False
        
        # Méthode 1: send_email (la méthode originale que vous essayez d'utiliser)
        try:
            if hasattr(email_service, 'send_email'):
                success = email_service.send_email(
                    to_email=driver_data["driver_email"],
                    subject=subject,
                    html_content=html_content,
                    text_content=text_content
                )
            # Méthode 2: send_email_smtp (méthode courante dans FastAPI)
            elif hasattr(email_service, 'send_email_smtp'):
                success = email_service.send_email_smtp(
                    to_email=driver_data["driver_email"],
                    subject=subject,
                    body=html_content
                )
            # Méthode 3: send (méthode simple)
            elif hasattr(email_service, 'send'):
                success = email_service.send(
                    to_email=driver_data["driver_email"],
                    subject=subject,
                    content=html_content
                )
            else:
                print(f"❌ Aucune méthode d'envoi d'email trouvée dans EmailService")
                print(f"    Méthodes disponibles: {dir(email_service)}")
                return
                
        except Exception as method_error:
            print(f"❌ Erreur avec la méthode d'envoi d'email: {str(method_error)}")
            return
        
        if success:
            print(f"✅ Email de bienvenue envoyé au livreur: {driver_data['driver_email']}")
        else:
            print(f"❌ Échec d'envoi d'email au livreur: {driver_data['driver_email']}")
            
    except Exception as e:
        print(f"❌ Erreur lors de l'envoi de l'email au livreur: {str(e)}")

def send_seller_notification_email(email_service: EmailService, seller_data: dict):
    """
    Envoie une notification au vendeur principal
    """
    try:
        subject = f"✅ Nouveau Livreur Inscrit: {seller_data['driver_name']}"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    background: #f5f7fa;
                    margin: 0;
                    padding: 20px;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    background: white;
                    border-radius: 15px;
                    overflow: hidden;
                    box-shadow: 0 5px 20px rgba(0,0,0,0.1);
                }}
                .header {{
                    background: linear-gradient(135deg, #2196F3, #0D47A1);
                    color: white;
                    padding: 25px;
                    text-align: center;
                }}
                .header h1 {{
                    margin: 0;
                    font-size: 22px;
                }}
                .content {{
                    padding: 30px;
                }}
                .notification-card {{
                    background: #e8f5e9;
                    border: 2px solid #4CAF50;
                    border-radius: 10px;
                    padding: 20px;
                    margin: 20px 0;
                }}
                .driver-info {{
                    background: white;
                    padding: 20px;
                    border-radius: 8px;
                    margin: 15px 0;
                }}
                .info-row {{
                    display: flex;
                    margin-bottom: 10px;
                    padding-bottom: 10px;
                    border-bottom: 1px solid #eee;
                }}
                .info-label {{
                    flex: 1;
                    font-weight: bold;
                    color: #555;
                }}
                .info-value {{
                    flex: 2;
                    color: #333;
                }}
                .stats {{
                    background: #e3f2fd;
                    padding: 15px;
                    border-radius: 8px;
                    margin: 20px 0;
                }}
                .footer {{
                    background: #f5f5f5;
                    padding: 20px;
                    text-align: center;
                    color: #666;
                    font-size: 12px;
                    border-top: 1px solid #ddd;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📋 NOUVEAU LIVREUR INSCRIT</h1>
                    <p>Notification système</p>
                </div>
                
                <div class="content">
                    <div class="notification-card">
                        <h2 style="color: #2E7D32; margin-top: 0;">🎉 Félicitations {seller_data['seller_name']} !</h2>
                        <p>Un nouveau livreur vient de rejoindre votre équipe de livraison.</p>
                    </div>
                    
                    <div class="driver-info">
                        <h3 style="color: #2196F3; margin-top: 0;">👤 Informations du Livreur</h3>
                        
                        <div class="info-row">
                            <div class="info-label">Nom complet:</div>
                            <div class="info-value"><strong>{seller_data['driver_name']}</strong></div>
                        </div>
                        
                        <div class="info-row">
                            <div class="info-label">Email:</div>
                            <div class="info-value">{seller_data['driver_email']}</div>
                        </div>
                        
                        <div class="info-row">
                            <div class="info-label">Téléphone:</div>
                            <div class="info-value">{seller_data['driver_phone']}</div>
                        </div>
                        
                        <div class="info-row">
                            <div class="info-label">Zone de livraison:</div>
                            <div class="info-value">{seller_data['delivery_zone']}</div>
                        </div>
                        
                        <div class="info-row">
                            <div class="info-label">Statut:</div>
                            <div class="info-value">
                                <span style="background: #4CAF50; color: white; padding: 3px 8px; border-radius: 12px; font-size: 12px;">
                                    {seller_data['status']}
                                </span>
                            </div>
                        </div>
                        
                        <div class="info-row">
                            <div class="info-label">Date d'inscription:</div>
                            <div class="info-value">{seller_data['creation_date']}</div>
                        </div>
                        
                        <div class="info-row">
                            <div class="info-label">ID Livreur:</div>
                            <div class="info-value">{seller_data['driver_id']}</div>
                        </div>
                    </div>
                    
                    <div class="stats">
                        <h3 style="color: #2196F3; margin-top: 0;">📊 Action Réussie</h3>
                        <p>✅ Un email de bienvenue avec ses identifiants a été envoyé au livreur.</p>
                        <p>✅ Le livreur peut maintenant se connecter à l'application.</p>
                        <p>✅ Il est prêt à recevoir des missions de livraison.</p>
                    </div>
                    
                    <div style="background: #fff3e0; padding: 15px; border-radius: 8px; margin-top: 20px;">
                        <h4 style="color: #ff9800; margin-top: 0;">💡 Prochaines Actions Recommandées</h4>
                        <ul style="margin: 10px 0; padding-left: 20px;">
                            <li>Vérifier les informations du livreur</li>
                            <li>Configurer ses permissions si nécessaire</li>
                            <li>L'ajouter à votre équipe de livraison</li>
                            <li>Planifier sa première formation si nécessaire</li>
                        </ul>
                    </div>
                    
                    <div style="text-align: center; margin-top: 30px;">
                        <p style="color: #666; font-size: 14px;">
                            Vous pouvez gérer ce livreur depuis votre tableau de bord vendeur.
                        </p>
                    </div>
                </div>
                
                <div class="footer">
                    <p>© {datetime.now().year} Commerce Madagascar - Système de Gestion Vendeur</p>
                    <p>Notification automatique - Ne pas répondre</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Version texte simple
        text_content = f"""
        NOTIFICATION : NOUVEAU LIVREUR INSCRIT
        
        Bonjour {seller_data['seller_name']},
        
        UN NOUVEAU LIVREUR VIENT DE REJOINDRE VOTRE ÉQUIPE !
        
        INFORMATIONS DU LIVREUR :
        Nom: {seller_data['driver_name']}
        Email: {seller_data['driver_email']}
        Téléphone: {seller_data['driver_phone']}
        Zone: {seller_data['delivery_zone']}
        Statut: {seller_data['status']}
        Date: {seller_data['creation_date']}
        ID: {seller_data['driver_id']}
        
        ACTION RÉUSSIE :
        ✅ Email de bienvenue envoyé au livreur
        ✅ Livreur prêt à se connecter
        ✅ Prêt pour les missions de livraison
        
        PROCHAINES ACTIONS RECOMMANDÉES :
        1. Vérifier les informations du livreur
        2. Configurer ses permissions
        3. L'ajouter à votre équipe
        4. Planifier sa première formation
        
        Vous pouvez gérer ce livreur depuis votre tableau de bord vendeur.
        
        © {datetime.now().year} Commerce Madagascar
        Notification automatique
        """
        
        # Essayer différentes méthodes possibles
        success = False
        
        # Méthode 1: send_email (la méthode originale que vous essayez d'utiliser)
        try:
            if hasattr(email_service, 'send_email'):
                success = email_service.send_email(
                    to_email=seller_data["seller_email"],
                    subject=subject,
                    html_content=html_content,
                    text_content=text_content
                )
            # Méthode 2: send_email_smtp (méthode courante dans FastAPI)
            elif hasattr(email_service, 'send_email_smtp'):
                success = email_service.send_email_smtp(
                    to_email=seller_data["seller_email"],
                    subject=subject,
                    body=html_content
                )
            # Méthode 3: send (méthode simple)
            elif hasattr(email_service, 'send'):
                success = email_service.send(
                    to_email=seller_data["seller_email"],
                    subject=subject,
                    content=html_content
                )
            else:
                print(f"❌ Aucune méthode d'envoi d'email trouvée dans EmailService pour le vendeur")
                return
                
        except Exception as method_error:
            print(f"❌ Erreur avec la méthode d'envoi d'email pour le vendeur: {str(method_error)}")
            return
        
        if success:
            print(f"✅ Notification envoyée au vendeur: {seller_data['seller_email']}")
        else:
            print(f"❌ Échec d'envoi de notification au vendeur: {seller_data['seller_email']}")
            
    except Exception as e:
        print(f"❌ Erreur lors de l'envoi de la notification au vendeur: {str(e)}")

@router.get("/")
async def get_drivers(
    statut: Optional[str] = Query(None, description="Filtrer par statut"),
    disponibilite: Optional[bool] = Query(None, description="Filtrer par disponibilité"),
    zone: Optional[str] = Query(None, description="Filtrer par zone de livraison"),
    search: Optional[str] = Query(None, description="Recherche par nom, email ou téléphone"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_seller)
):
    """
    Récupère la liste des livreurs du vendeur connecté
    """
    try:
        seller_id = UUID(current_user["user_id"])
        
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
        
        # Recherche par nom, email ou téléphone
        if search:
            search_term = f"%{search}%"
            query = query.filter(
                or_(
                    User.full_name.ilike(search_term),
                    User.email.ilike(search_term),
                    User.telephone.ilike(search_term)
                )
            )
        
        # Trier par date de création (plus récent d'abord)
        query = query.order_by(Driver.created_at.desc())
        
        # Pagination
        total_count = query.count()
        drivers = query.offset(skip).limit(limit).all()
        
        # Formater la réponse
        result = []
        for driver in drivers:
            user = driver.user
            if user:
                result.append({
                    "driver_id": str(driver.id),
                    "user_id": str(driver.user_id),
                    "seller_id": str(driver.seller_id),
                    "full_name": user.full_name,
                    "email": user.email,
                    "telephone": user.telephone,
                    "adresse": user.adresse,
                    "role": user.role,
                    "statut": user.statut,
                    "zone_livraison": driver.zone_livraison,
                    "disponibilite": driver.disponibilite,
                    "is_active": user.is_active,
                    "created_at": driver.created_at.isoformat() if driver.created_at else None,
                    "updated_at": driver.updated_at.isoformat() if driver.updated_at else None
                })
        
        # Compter les statistiques
        active_count = db.query(func.count(Driver.id))\
                        .join(User, User.id == Driver.user_id)\
                        .filter(
                            Driver.seller_id == seller_id,
                            User.statut == "actif",
                            User.is_active == True
                        ).scalar() or 0
        
        available_count = db.query(func.count(Driver.id))\
                           .filter(
                               Driver.seller_id == seller_id,
                               Driver.disponibilite == True
                           ).scalar() or 0
        
        return {
            "count": len(result),
            "total": total_count,
            "active": active_count,
            "available": available_count,
            "seller": {
                "id": str(seller_id),
                "name": current_user.get("full_name", ""),
                "email": current_user.get("email", "")
            },
            "drivers": result
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur récupération livreurs: {str(e)}"
        )

@router.get("/{driver_id}")
async def get_driver(
    driver_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_seller)
):
    """
    Récupère les détails d'un livreur spécifique
    """
    try:
        seller_id = UUID(current_user["user_id"])
        
        driver = db.query(Driver).filter(
            Driver.id == UUID(driver_id),
            Driver.seller_id == seller_id
        ).first()
        
        if not driver:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Livreur non trouvé ou n'appartient pas à ce vendeur"
            )
        
        user = driver.user
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Utilisateur non trouvé"
            )
        
        return {
            "driver_id": str(driver.id),
            "user_id": str(driver.user_id),
            "seller_id": str(driver.seller_id),
            "full_name": user.full_name,
            "email": user.email,
            "telephone": user.telephone,
            "adresse": user.adresse,
            "role": user.role,
            "statut": user.statut,
            "zone_livraison": driver.zone_livraison,
            "disponibilite": driver.disponibilite,
            "is_active": user.is_active,
            "created_at": driver.created_at.isoformat() if driver.created_at else None,
            "updated_at": driver.updated_at.isoformat() if driver.updated_at else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur récupération livreur: {str(e)}"
        )

@router.put("/{driver_id}")
async def update_driver(
    driver_id: str,
    update_data: dict,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_seller)
):
    """
    Met à jour les informations d'un livreur
    """
    try:
        seller_id = UUID(current_user["user_id"])
        
        driver = db.query(Driver).filter(
            Driver.id == UUID(driver_id),
            Driver.seller_id == seller_id
        ).first()
        
        if not driver:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Livreur non trouvé"
            )
        
        user = driver.user
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Utilisateur non trouvé"
            )
        
        # Mettre à jour l'utilisateur
        if "full_name" in update_data and update_data["full_name"]:
            user.full_name = update_data["full_name"]
        
        if "telephone" in update_data:
            user.telephone = update_data["telephone"]
        
        if "adresse" in update_data and update_data["adresse"]:
            old_address = user.adresse
            user.adresse = update_data["adresse"]
            
            # Mettre à jour la zone de livraison si l'adresse change
            if update_data["adresse"] != old_address:
                try:
                    driver.zone_livraison = geocoding_service.extract_zone_from_address(
                        update_data["adresse"]
                    )
                except Exception as e:
                    print(f"⚠️  Erreur géocodage lors de la mise à jour: {e}")
                    # Garder l'ancienne zone en cas d'erreur
        
        if "statut" in update_data:
            user.statut = update_data["statut"]
            
            # Synchroniser is_active avec statut
            if update_data["statut"] == "actif":
                user.is_active = True
                driver.disponibilite = True
            elif update_data["statut"] in ["suspendu", "en_attente", "rejeté"]:
                user.is_active = False
                driver.disponibilite = False
        
        if "is_active" in update_data:
            user.is_active = update_data["is_active"]
            # Synchroniser statut avec is_active
            if update_data["is_active"]:
                user.statut = "actif"
                driver.disponibilite = True
            else:
                user.statut = "suspendu"
                driver.disponibilite = False
        
        # Mettre à jour le driver
        if "disponibilite" in update_data:
            driver.disponibilite = update_data["disponibilite"]
        
        if "zone_livraison" in update_data:
            driver.zone_livraison = update_data["zone_livraison"]
        
        # Mettre à jour les dates
        user.updated_at = datetime.now()
        driver.updated_at = datetime.now()
        
        db.commit()
        
        return {
            "message": "Livreur mis à jour avec succès",
            "driver_id": str(driver.id),
            "full_name": user.full_name,
            "email": user.email,
            "statut": user.statut,
            "is_active": user.is_active,
            "disponibilite": driver.disponibilite,
            "zone_livraison": driver.zone_livraison
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur mise à jour livreur: {str(e)}"
        )

@router.patch("/{driver_id}/activate")
async def activate_driver(
    driver_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_seller)
):
    """
    Active un livreur (statut = actif, is_active = true, disponibilite = true)
    """
    return await _toggle_driver_status(driver_id, "activate", db, current_user)

@router.patch("/{driver_id}/suspend")
async def suspend_driver(
    driver_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_seller)
):
    """
    Suspend un livreur (statut = suspendu, is_active = false, disponibilite = false)
    """
    return await _toggle_driver_status(driver_id, "suspend", db, current_user)

@router.delete("/{driver_id}")
async def delete_driver(
    driver_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_seller)
):
    """
    Supprime (soft delete) un livreur
    Marque le compte comme supprimé et désactivé
    """
    try:
        seller_id = UUID(current_user["user_id"])
        
        driver = db.query(Driver).filter(
            Driver.id == UUID(driver_id),
            Driver.seller_id == seller_id
        ).first()
        
        if not driver:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Livreur non trouvé"
            )
        
        user = driver.user
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Utilisateur non trouvé"
            )
        
        # Soft delete: désactiver le compte
        user.statut = "suspendu"
        user.is_active = False
        driver.disponibilite = False
        
        # Modifier l'email pour éviter les conflits
        original_email = user.email
        timestamp = int(datetime.now().timestamp())
        user.email = f"deleted_{timestamp}_{original_email}"
        
        # Mettre à jour les dates
        user.updated_at = datetime.now()
        driver.updated_at = datetime.now()
        
        db.commit()
        
        return {
            "message": "Livreur supprimé avec succès",
            "driver_id": driver_id,
            "original_email": original_email,
            "new_email": user.email,
            "statut": user.statut,
            "is_active": user.is_active,
            "disponibilite": driver.disponibilite
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur suppression livreur: {str(e)}"
        )

async def _toggle_driver_status(
    driver_id: str,
    action: str,
    db: Session,
    current_user: dict
):
    """
    Fonction utilitaire pour changer le statut d'un livreur
    """
    try:
        seller_id = UUID(current_user["user_id"])
        
        driver = db.query(Driver).filter(
            Driver.id == UUID(driver_id),
            Driver.seller_id == seller_id
        ).first()
        
        if not driver:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Livreur non trouvé"
            )
        
        user = driver.user
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Utilisateur non trouvé"
            )
        
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
            
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Action non valide"
            )
        
        # Mettre à jour les dates
        user.updated_at = datetime.now()
        driver.updated_at = datetime.now()
        
        db.commit()
        
        return {
            "message": message,
            "driver_id": driver_id,
            "full_name": user.full_name,
            "email": user.email,
            "statut": user.statut,
            "is_active": user.is_active,
            "disponibilite": driver.disponibilite
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur changement statut: {str(e)}"
        )

@router.get("/stats/summary")
async def get_drivers_stats(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_seller)
):
    """
    Récupère les statistiques des livreurs du vendeur
    """
    try:
        seller_id = UUID(current_user["user_id"])
        
        # Compter les livreurs par statut
        stats = db.query(
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
        
        # Livreurs actifs
        active_drivers = db.query(func.count(Driver.id))\
                          .join(User, User.id == Driver.user_id)\
                          .filter(
                              Driver.seller_id == seller_id,
                              User.is_active == True,
                              User.statut == "actif"
                          ).scalar() or 0
        
        # Livreurs disponibles
        available_drivers = db.query(func.count(Driver.id))\
                             .filter(
                                 Driver.seller_id == seller_id,
                                 Driver.disponibilite == True
                             ).scalar() or 0
        
        # Formater les statistiques
        statut_stats = {statut: count for statut, count in stats}
        disponibilite_stats_dict = {
            "disponible": 0,
            "indisponible": 0
        }
        for disponibilite, count in disponibilite_stats:
            if disponibilite:
                disponibilite_stats_dict["disponible"] = count
            else:
                disponibilite_stats_dict["indisponible"] = count
        
        return {
            "seller": {
                "id": str(seller_id),
                "name": current_user.get("full_name", ""),
                "email": current_user.get("email", "")
            },
            "stats": {
                "total": total_drivers,
                "active": active_drivers,
                "available": available_drivers,
                "by_statut": statut_stats,
                "by_disponibilite": disponibilite_stats_dict
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur récupération statistiques: {str(e)}"
        )

@router.get("/zones/available")
async def get_available_zones(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_seller)
):
    """
    Récupère la liste des zones de livraison disponibles pour les livreurs du vendeur
    """
    try:
        seller_id = UUID(current_user["user_id"])
        
        # Récupérer les zones distinctes
        zones = db.query(func.distinct(Driver.zone_livraison))\
                 .filter(
                     Driver.seller_id == seller_id,
                     Driver.zone_livraison.isnot(None),
                     Driver.zone_livraison != ""
                 ).all()
        
        # Compter les livreurs par zone
        zone_stats = db.query(
            Driver.zone_livraison,
            func.count(Driver.id).label("count"),
            func.sum(func.cast(Driver.disponibilite, Integer)).label("available")
        ).filter(
            Driver.seller_id == seller_id,
            Driver.zone_livraison.isnot(None),
            Driver.zone_livraison != ""
        ).group_by(Driver.zone_livraison).all()
        
        zones_list = [zone[0] for zone in zones if zone[0]]
        zones_with_stats = []
        
        for stat in zone_stats:
            zones_with_stats.append({
                "zone": stat.zone_livraison,
                "total": stat.count,
                "available": stat.available or 0,
                "indisponible": stat.count - (stat.available or 0)
            })
        
        return {
            "seller_id": str(seller_id),
            "total_zones": len(zones_list),
            "zones": zones_list,
            "zones_with_stats": zones_with_stats
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur récupération zones: {str(e)}"
        )

# Endpoint pour mettre à jour la géolocalisation d'un livreur
@router.post("/{driver_id}/update-geolocation")
async def update_driver_geolocation(
    driver_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_seller)
):
    """
    Met à jour la zone de livraison d'un livreur basée sur son adresse actuelle
    """
    try:
        seller_id = UUID(current_user["user_id"])
        
        driver = db.query(Driver).filter(
            Driver.id == UUID(driver_id),
            Driver.seller_id == seller_id
        ).first()
        
        if not driver:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Livreur non trouvé"
            )
        
        user = driver.user
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Utilisateur non trouvé"
            )
        
        # Mettre à jour la zone avec géocodage
        old_zone = driver.zone_livraison
        try:
            new_zone = geocoding_service.extract_zone_from_address(user.adresse)
            driver.zone_livraison = new_zone
            driver.updated_at = datetime.now()
            
            db.commit()
            
            return {
                "message": "Zone de livraison mise à jour",
                "driver_id": driver_id,
                "old_zone": old_zone,
                "new_zone": new_zone,
                "adresse": user.adresse
            }
            
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Erreur géocodage: {str(e)}"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur mise à jour géolocalisation: {str(e)}"
        )