# app/main.py - VERSION PRODUCTION FINALE AVEC ROUTES FACEBOOK COMPLÈTES
import os
import sys
from datetime import datetime
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from app.api.v1.endpoints import orders
from app.api.v1.endpoints import facebook_auto_reply, facebook_messenger  # AJOUT: Import du module facebook_messenger

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('app.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# Configuration
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

print(f"🚀 Live Commerce API")
print(f"📁 Répertoire: {current_dir}")
logger.info(f"Application démarrée depuis: {current_dir}")

# ================================
#   INITIALISATION DB
# ================================
print("\n🗄️ BASE DE DONNÉES")

try:
    from app.db import engine, Base
    from app.core.config import settings
    from sqlalchemy import text
    
    # Test connexion DB
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    
    db_info = settings.DATABASE_URL.split('@')[1] if '@' in settings.DATABASE_URL else 'PostgreSQL'
    print(f"✅ Connectée: {db_info}")
    logger.info(f"Base de données connectée: {db_info}")
    
    # ⭐ IMPORTANT: Importez TOUS les modèles avant create_all()
    from app.models.user import User
    from app.models.seller import Seller
    from app.models.driver_model import Driver
    from app.models.product import Product
    from app.models.order import Order, OrderItem
    
    # Importez les modèles Facebook
    from app.models.facebook import (
        FacebookUser, FacebookPage, FacebookPost,
        FacebookLiveVideo, FacebookComment, FacebookMessage,
        FacebookMessageTemplate, FacebookWebhookLog, 
        FacebookWebhookSubscription, NLPProcessingLog
    )
    
    # Création des tables
    Base.metadata.create_all(bind=engine)
    print("✅ Tables initialisées")
    logger.info("Tables de base de données créées avec succès")
    
except ImportError as e:
    print(f"⚠️  Erreur d'import de modèle: {e}")
    logger.error(f"Erreur d'import de modèle: {e}")
except Exception as e:
    print(f"⚠️  Erreur DB: {e}")
    logger.error(f"Erreur base de données: {e}", exc_info=True)

# ================================
#   APPLICATION
# ================================
app = FastAPI(
    title="Live Commerce API",
    description="Système complet de commerce avec génération automatique de codes produits et intégration Facebook avancée",
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    contact={
        "name": "Support Live Commerce",
        "email": "support@livecommerce.com",
    },
    license_info={
        "name": "Proprietary",
        "url": "https://livecommerce.com/terms",
    }
)

# CORS configuration
from app.core.config import settings

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:53514",
        "http://localhost:*",
        "http://127.0.0.1:*",
        "*"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=600,
)

# ================================
#   INITIALISATION DES SERVICES
# ================================
print("\n" + "="*50)
print("⚙️  INITIALISATION DES SERVICES")
print("="*50)

services_loaded = {}

# Service NLP
try:
    from app.services import nlp_service
    if nlp_service:
        services_loaded["nlp"] = True
        print(f"✅ Service NLP → Initialisé")
        logger.info("Service NLP initialisé avec succès")
    else:
        services_loaded["nlp"] = False
        print(f"⚠️  Service NLP: Non initialisé (configuration manquante)")
        logger.warning("Service NLP non initialisé")
except ImportError as e:
    print(f"⚠️  Service NLP: Module non trouvé - {e}")
    services_loaded["nlp"] = False
    logger.warning(f"Service NLP non initialisé: Module non trouvé: {e}")
except Exception as e:
    print(f"⚠️  Service NLP: Erreur d'initialisation - {e}")
    services_loaded["nlp"] = False
    logger.warning(f"Service NLP non initialisé: {e}")

# Service Facebook Graph API
try:
    from app.services.facebook_graph_api import FacebookGraphAPIService
    facebook_graph_service = FacebookGraphAPIService()
    services_loaded["facebook_graph"] = True
    print(f"✅ Facebook Graph API → Initialisé")
    logger.info("Service Facebook Graph API initialisé avec succès")
except Exception as e:
    print(f"⚠️  Facebook Graph API: {e}")
    services_loaded["facebook_graph"] = False
    logger.warning(f"Service Facebook Graph API non initialisé: {e}")

# Service Facebook Webhook
try:
    from app.services.facebook_webhook import FacebookWebhookService
    facebook_webhook_service = FacebookWebhookService()
    services_loaded["facebook_webhook"] = True
    print(f"✅ Facebook Webhook → Initialisé")
    logger.info("Service Facebook Webhook initialisé avec succès")
except Exception as e:
    print(f"⚠️  Facebook Webhook: {e}")
    services_loaded["facebook_webhook"] = False
    logger.warning(f"Service Facebook Webhook non initialisé: {e}")

# Service OCR
try:
    from app.services.ocr_service import OCRService
    ocr_config = {
        "OCR_ENGINE": "paddleocr",
        "PADDLE_OCR_LANGS": ["fr", "en", "mg"],
        "MAX_CONCURRENT_OCR": 4,
        "OCR_TIMEOUT": 30
    }
    services_loaded["ocr"] = True
    print(f"✅ Service OCR → Initialisé")
    logger.info("Service OCR initialisé avec succès")
except ImportError:
    print(f"⚠️  Service OCR: Module non trouvé (optionnel)")
    services_loaded["ocr"] = False
except Exception as e:
    print(f"⚠️  Service OCR: Erreur d'initialisation - {e}")
    services_loaded["ocr"] = False
    logger.warning(f"Service OCR non initialisé: {e}")

print("="*50)
print(f"✅ Services chargés: {sum(services_loaded.values())}/{len(services_loaded)}")

# ================================
#   CHARGEMENT DES ROUTEURS
# ================================
print("\n" + "="*50)
print("📦 CHARGEMENT DES ROUTEURS")
print("="*50)

# Dictionnaire pour suivre les routeurs chargés
loaded_routers = {}

# ===== ROUTER ORDERS (NOUVEAU) =====
try:
    # Inclure le routeur orders
    app.include_router(
        orders.router,
        prefix="/api/v1",
        tags=["orders"]
    )
    loaded_routers["orders"] = "/api/v1"
    print(f"✅ Orders → /api/v1/orders")
    print(f"   🛒 Gestion complète des commandes")
    print(f"   📊 Statistiques et rapports")
    print(f"   🤖 Intégration Facebook automatique")
    logger.info("Routeur Orders chargé avec succès")
except Exception as e:
    print(f"❌ Orders: {e}")
    logger.error(f"Échec chargement Orders: {e}")

# ===== ROUTER FACEBOOK AUTO REPLY =====
try:
    app.include_router(
        facebook_auto_reply.router,
        prefix="/api/v1",
        tags=["facebook-auto-reply"]
    )
    loaded_routers["facebook_auto_reply"] = "/api/v1"
    print(f"✅ Facebook Auto Reply → /api/v1/facebook/auto-reply")
    print(f"   🤖 Réponses automatiques IA")
    print(f"   💬 Gestion des commentaires")
    print(f"   📊 Analytics de performance")
    logger.info("Routeur Facebook Auto Reply chargé avec succès")
except ImportError as e:
    print(f"⚠️  Facebook Auto Reply: Module non trouvé - {e}")
    logger.warning(f"Module Facebook Auto Reply non trouvé: {e}")
except Exception as e:
    print(f"❌ Facebook Auto Reply: {e}")
    logger.error(f"Échec chargement Facebook Auto Reply: {e}")

# ===== ROUTER FACEBOOK MESSENGER =====
try:
    app.include_router(
        facebook_messenger.router,
        prefix="/api/v1",
        tags=["facebook-messenger"]
    )
    loaded_routers["facebook_messenger"] = "/api/v1"
    print(f"✅ Facebook Messenger → /api/v1/facebook/messenger")
    print(f"   💬 Gestion des messages privés")
    print(f"   📨 Webhook Messenger")
    print(f"   🔄 Traitement automatisé")
    print(f"   📊 Historique des messages")
    logger.info("Routeur Facebook Messenger chargé avec succès")
except ImportError as e:
    print(f"⚠️  Facebook Messenger: Module non trouvé - {e}")
    logger.warning(f"Module Facebook Messenger non trouvé: {e}")
except Exception as e:
    print(f"❌ Facebook Messenger: {e}")
    logger.error(f"Échec chargement Facebook Messenger: {e}")

# Routeur Authentication
try:
    from app.routers.auth_router import router as auth_router
    app.include_router(auth_router)
    loaded_routers["auth"] = auth_router.prefix
    print(f"✅ Authentication → {auth_router.prefix}")
    logger.info(f"Routeur authentification chargé: {auth_router.prefix}")
except Exception as e:
    print(f"❌ Authentication: {e}")
    logger.error(f"Échec chargement authentification: {e}")

# Routeur Drivers
try:
    from app.routers.drivers import router as drivers_router
    app.include_router(drivers_router)
    loaded_routers["drivers"] = drivers_router.prefix
    print(f"✅ Drivers → {drivers_router.prefix}")
    logger.info(f"Routeur drivers chargé: {drivers_router.prefix}")
except Exception as e:
    print(f"❌ Drivers: {e}")
    logger.error(f"Échec chargement drivers: {e}")

# Routeur Products
try:
    from app.routers.product import router as product_router
    app.include_router(product_router)
    loaded_routers["products"] = product_router.prefix
    print(f"✅ Products → {product_router.prefix}")
    print(f"   ⭐ Nouveau système avec génération auto de codes")
    logger.info(f"Routeur produits chargé: {product_router.prefix}")
except Exception as e:
    print(f"❌ Products: {e}")
    logger.error(f"Échec chargement produits: {e}")

# Routeur OCR
try:
    from app.api.endpoints.ocr import router as ocr_router
    app.include_router(ocr_router)
    loaded_routers["ocr"] = ocr_router.prefix
    print(f"✅ OCR/NLP → {ocr_router.prefix}")
    print(f"   📷 Image OCR")
    print(f"   📄 PDF OCR")
    print(f"   📝 Document OCR")
    print(f"   📊 Excel OCR")
    print(f"   📋 Form processing")
    print(f"   🛒 Order extraction")
    logger.info(f"Routeur OCR/NLP chargé: {ocr_router.prefix}")
except ImportError as e:
    print(f"⚠️  OCR/NLP: Module non trouvé - {e}")
    logger.warning(f"Module OCR/NLP non trouvé: {e}")
except AttributeError as e:
    print(f"⚠️  OCR/NLP: Routeur mal configuré - {e}")
    logger.error(f"Routeur OCR/NLP mal configuré: {e}")
except Exception as e:
    print(f"⚠️  OCR/NLP: Erreur de chargement - {e}")
    logger.error(f"Échec chargement OCR/NLP: {e}")
    from fastapi import APIRouter, HTTPException
    fallback_router = APIRouter()
    @fallback_router.get("/", include_in_schema=False)
    async def ocr_unavailable():
        raise HTTPException(status_code=503, detail="Le service OCR est temporairement indisponible.")
    app.include_router(fallback_router, prefix="/ocr", tags=["OCR"])
    logger.info("Routeur de secours OCR créé (service indisponible).")

# ================================
#   ROUTES FACEBOOK COMPLÈTES
# ================================
print("\n" + "="*30)
print("📱 INTÉGRATION FACEBOOK COMPLÈTE")
print("="*30)

facebook_loaded = False
facebook_routes_count = 0

try:
    from app.api.v1.endpoints.facebook import router as facebook_router
    app.include_router(
        facebook_router,
        prefix="/api/v1/facebook",
        tags=["facebook"]
    )
    facebook_routes_count = len(facebook_router.routes)
    loaded_routers["facebook"] = "/api/v1/facebook"
    facebook_loaded = True
    
    print(f"✅ Facebook → /api/v1/facebook ({facebook_routes_count} routes)")
    print(f"   🔐 OAuth:         /login")
    print(f"   🔄 Callback:      /callback")
    print(f"   📄 Pages:         /pages")
    print(f"   🎯 Sélection:     /pages/select")
    print(f"   ❌ Déconnexion:   /disconnect")
    print(f"   🔗 Webhook:       /webhook")
    print(f"   📝 Webhook Sub:   /webhook/subscribe")
    print(f"   📡 Stream:        /webhook/stream")
    print(f"   🩺 Health:        /webhook/health")
    print(f"   🔄 Synchronisation:")
    print(f"     • /sync           - Sync complète")
    print(f"     • /sync/start-periodic - Sync périodique")
    print(f"   📊 Analytics:     /live/{id}/analytics")
    print(f"   💬 Gestion Messages:")
    print(f"     • /messages/{id}/reply - Répondre aux messages")
    print(f"     • /comments          - Liste commentaires")
    print(f"     • /comments/bulk-process - Traitement en masse")
    print(f"   📥 Export:        /export/comments")
    print(f"   🔔 Notifications: /notifications/recent")
    print(f"   🛠️  Debug:        /debug/seller-info")
    
    logger.info(f"Routeur Facebook chargé avec succès ({facebook_routes_count} routes)")
    
except ImportError as e:
    print(f"⚠️  Facebook: Module non trouvé - {e}")
    print("   Vérifiez que le fichier app/api/v1/endpoints/facebook.py existe")
    logger.warning(f"Module Facebook non trouvé: {e}", exc_info=True)
except Exception as e:
    print(f"❌ Facebook: {e}")
    logger.error(f"Échec chargement Facebook: {e}", exc_info=True)

# ================================
#   NOUVELLES ROUTES API (GROUPÉES)
# ================================
print("\n" + "="*30)
print("🆕 NOUVELLES ROUTES API")
print("="*30)

# Routeurs additionnels
additional_routers = {}

# Routeur Analytics
try:
    from app.api.v1.endpoints.analytics import router as analytics_router
    app.include_router(
        analytics_router,
        prefix="/api/v1/analytics",
        tags=["analytics"]
    )
    additional_routers["analytics"] = "/api/v1/analytics"
    print(f"✅ Analytics → /api/v1/analytics")
    logger.info("Routeur Analytics chargé")
except ImportError:
    print(f"⚠️  Analytics: Module non trouvé (optionnel)")
except Exception as e:
    print(f"⚠️  Analytics: {e}")

# Routeur Notifications
try:
    from app.api.v1.endpoints.notifications import router as notifications_router
    app.include_router(
        notifications_router,
        prefix="/api/v1/notifications",
        tags=["notifications"]
    )
    additional_routers["notifications"] = "/api/v1/notifications"
    print(f"✅ Notifications → /api/v1/notifications")
    logger.info("Routeur Notifications chargé")
except ImportError:
    print(f"⚠️  Notifications: Module non trouvé (optionnel)")
except Exception as e:
    print(f"⚠️  Notifications: {e}")

# Routeur Reports
try:
    from app.api.v1.endpoints.reports import router as reports_router
    app.include_router(
        reports_router,
        prefix="/api/v1/reports",
        tags=["reports"]
    )
    additional_routers["reports"] = "/api/v1/reports"
    print(f"✅ Reports → /api/v1/reports")
    logger.info("Routeur Reports chargé")
except ImportError:
    print(f"⚠️  Reports: Module non trouvé (optionnel)")
except Exception as e:
    print(f"⚠️  Reports: {e}")

print("="*50)
print(f"✅ Tous les routeurs chargés ({len(loaded_routers) + len(additional_routers)} modules)")
logger.info(f"Routeurs chargés: {list(loaded_routers.keys()) + list(additional_routers.keys())}")

# ================================
#   ENDPOINTS DE BASE AMÉLIORÉS
# ================================
@app.get("/", tags=["Root"], response_model=dict)
async def root():
    """Endpoint racine avec informations système complètes"""
    from app.db import engine
    from sqlalchemy import text
    
    db_status = "connected"
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            db_version = result.fetchone()[0]
    except Exception as e:
        db_status = f"error: {str(e)}"
        db_version = "unknown"
    
    return {
        "message": "🚀 Live Commerce API - Système Complet",
        "version": "3.0.0",
        "status": "operational",
        "timestamp": datetime.now().isoformat(),
        "environment": os.getenv("ENVIRONMENT", "production"),
        "system": {
            "database": {
                "status": db_status,
                "version": db_version.split()[0] if isinstance(db_version, str) else "unknown"
            },
            "services": services_loaded,
            "facebook_integration": {
                "status": "active" if facebook_loaded else "inactive",
                "routes_count": facebook_routes_count
            }
        },
        "endpoints": {
            "documentation": {
                "swagger": "/docs",
                "redoc": "/redoc",
                "openapi": "/openapi.json"
            },
            "health": "/health",
            "status": "/status",
            "modules": {
                **loaded_routers,
                **additional_routers
            }
        },
        "features": {
            "authentication": "active" if "auth" in loaded_routers else "inactive",
            "products": "active" if "products" in loaded_routers else "inactive",
            "drivers": "active" if "drivers" in loaded_routers else "inactive",
            "orders": "active" if "orders" in loaded_routers else "inactive",
            "facebook_auto_reply": "active" if "facebook_auto_reply" in loaded_routers else "inactive",
            "facebook_messenger": "active" if "facebook_messenger" in loaded_routers else "inactive",
            "facebook": {
                "integration": "active" if facebook_loaded else "inactive",
                "webhook": "active" if services_loaded.get("facebook_webhook") else "inactive",
                "graph_api": "active" if services_loaded.get("facebook_graph") else "inactive",
                "nlp": "active" if services_loaded.get("nlp") else "inactive"
            },
            "analytics": "active" if "analytics" in additional_routers else "inactive",
            "notifications": "active" if "notifications" in additional_routers else "inactive",
            "reports": "active" if "reports" in additional_routers else "inactive"
        }
    }

@app.get("/health", tags=["Health"], response_model=dict)
async def health_check():
    """Vérification de santé complète de l'application"""
    from app.db import engine
    from sqlalchemy import text
    import psutil
    import platform
    
    health_status = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "system": {},
        "services": {},
        "dependencies": {}
    }
    
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1 as status, version() as version"))
            row = result.fetchone()
            health_status["dependencies"]["database"] = {
                "status": "connected",
                "version": row[1].split()[0] if row[1] else "unknown",
                "latency": "N/A"
            }
    except Exception as e:
        health_status["status"] = "degraded"
        health_status["dependencies"]["database"] = {
            "status": "disconnected",
            "error": str(e)
        }
    
    health_status["services"] = services_loaded
    health_status["modules"] = {
        **loaded_routers,
        **additional_routers
    }
    
    health_status["system"] = {
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "cpu_usage": f"{psutil.cpu_percent()}%",
        "memory_usage": f"{psutil.virtual_memory().percent}%",
        "disk_usage": f"{psutil.disk_usage('/').percent}%"
    }
    
    if 'app_start_time' in globals():
        uptime = datetime.now() - app_start_time
        health_status["uptime"] = {
            "seconds": int(uptime.total_seconds()),
            "human": str(uptime).split('.')[0]
        }
    
    return health_status

@app.get("/status", tags=["Status"], response_model=dict)
async def detailed_status():
    """Statut détaillé avec métriques de performance"""
    import time
    from app.db import engine
    from sqlalchemy import text
    
    status = {
        "api": "Live Commerce API",
        "version": "3.0.0",
        "environment": os.getenv("ENVIRONMENT", "production"),
        "timestamp": datetime.now().isoformat(),
        "performance": {},
        "connections": {},
        "features": {}
    }
    
    try:
        start_time = time.time()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_latency = (time.time() - start_time) * 1000
        status["performance"]["database_latency_ms"] = round(db_latency, 2)
        status["connections"]["database"] = "healthy"
    except Exception as e:
        status["connections"]["database"] = f"unhealthy: {str(e)}"
    
    if facebook_loaded:
        status["features"]["facebook"] = {
            "integration": "active",
            "routes_count": facebook_routes_count,
            "webhook_enabled": services_loaded.get("facebook_webhook", False),
            "graph_api_enabled": services_loaded.get("facebook_graph", False),
            "nlp_enabled": services_loaded.get("nlp", False)
        }
    else:
        status["features"]["facebook"] = {"integration": "inactive"}
    
    active_services = sum(services_loaded.values())
    total_services = len(services_loaded)
    status["services"] = {
        "active": active_services,
        "total": total_services,
        "ratio": f"{active_services}/{total_services}"
    }
    
    return status

@app.get("/api/facebook/status", tags=["Facebook"], response_model=dict)
async def facebook_status():
    """Statut détaillé de l'intégration Facebook"""
    from app.core.config import settings
    
    facebook_config = {
        "app_id_configured": bool(settings.FACEBOOK_APP_ID),
        "app_secret_configured": bool(settings.FACEBOOK_APP_SECRET),
        "webhook_token_configured": bool(settings.FACEBOOK_WEBHOOK_VERIFY_TOKEN),
        "api_version": settings.FACEBOOK_API_VERSION,
        "app_url": settings.APP_URL if hasattr(settings, 'APP_URL') else None
    }
    
    status = {
        "facebook_integration": "active" if facebook_loaded else "inactive",
        "configuration": facebook_config,
        "services": {
            "graph_api": services_loaded.get("facebook_graph", False),
            "webhook": services_loaded.get("facebook_webhook", False),
            "nlp": services_loaded.get("nlp", False)
        },
        "endpoints": {
            "authentication": {
                "oauth_login": "/api/v1/facebook/login",
                "oauth_callback": "/api/v1/facebook/callback",
                "disconnect": "/api/v1/facebook/disconnect"
            },
            "pages": {
                "list": "/api/v1/facebook/pages",
                "select": "/api/v1/facebook/pages/select"
            },
            "webhooks": {
                "subscribe": "/api/v1/facebook/webhook/subscribe",
                "endpoint": "/api/v1/facebook/webhook",
                "stream": "/api/v1/facebook/webhook/stream",
                "health": "/api/v1/facebook/webhook/health"
            },
            "data": {
                "sync": "/api/v1/facebook/sync",
                "periodic_sync": "/api/v1/facebook/sync/start-periodic",
                "export_comments": "/api/v1/facebook/export/comments"
            },
            "messaging": {
                "reply": "/api/v1/facebook/messages/{id}/reply",
                "list_comments": "/api/v1/facebook/comments",
                "bulk_process": "/api/v1/facebook/comments/bulk-process"
            },
            "analytics": {
                "live_analytics": "/api/v1/facebook/live/{id}/analytics"
            },
            "notifications": {
                "recent": "/api/v1/facebook/notifications/recent"
            },
            "debug": {
                "seller_info": "/api/v1/facebook/debug/seller-info"
            }
        } if facebook_loaded else {},
        "version": "2.0.0",
        "timestamp": datetime.now().isoformat()
    }
    
    return status

@app.get("/api/system/debug", tags=["System"], include_in_schema=False)
async def system_debug():
    """Endpoint de débogage système avancé (non inclus dans la documentation)"""
    import platform
    import psutil
    import socket
    import threading
    import gc
    
    system_info = {
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "architecture": platform.architecture(),
        "processor": platform.processor(),
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation()
    }
    
    resources = {
        "cpu": {
            "cores": psutil.cpu_count(logical=False),
            "logical_cores": psutil.cpu_count(logical=True),
            "usage_percent": psutil.cpu_percent(interval=1),
            "freq": psutil.cpu_freq()._asdict() if psutil.cpu_freq() else None
        },
        "memory": {
            "total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
            "available_gb": round(psutil.virtual_memory().available / (1024**3), 2),
            "used_gb": round(psutil.virtual_memory().used / (1024**3), 2),
            "percent": psutil.virtual_memory().percent
        },
        "disk": {
            "total_gb": round(psutil.disk_usage('/').total / (1024**3), 2),
            "used_gb": round(psutil.disk_usage('/').used / (1024**3), 2),
            "free_gb": round(psutil.disk_usage('/').free / (1024**3), 2),
            "percent": psutil.disk_usage('/').percent
        }
    }
    
    process = psutil.Process()
    process_info = {
        "pid": process.pid,
        "name": process.name(),
        "status": process.status(),
        "create_time": datetime.fromtimestamp(process.create_time()).isoformat(),
        "cpu_percent": process.cpu_percent(),
        "memory_percent": process.memory_percent(),
        "memory_rss_mb": round(process.memory_info().rss / (1024**2), 2),
        "memory_vms_mb": round(process.memory_info().vms / (1024**2), 2),
        "num_threads": process.num_threads(),
        "connections": len(process.connections())
    }
    
    threads = threading.enumerate()
    thread_info = {
        "count": len(threads),
        "names": [t.name for t in threads]
    }
    
    gc_info = {
        "enabled": gc.isenabled(),
        "threshold": gc.get_threshold(),
        "count": gc.get_count()
    }
    
    app_info = {
        "loaded_routers": loaded_routers,
        "additional_routers": additional_routers,
        "facebook_loaded": facebook_loaded,
        "facebook_routes": facebook_routes_count,
        "services_loaded": services_loaded,
        "log_file": "app.log",
        "start_time": app_start_time.isoformat() if 'app_start_time' in globals() else None
    }
    
    network_info = {
        "hostname": socket.gethostname(),
        "ip": socket.gethostbyname(socket.gethostname()),
        "port": 8000
    }
    
    return {
        "timestamp": datetime.now().isoformat(),
        "system": system_info,
        "resources": resources,
        "process": process_info,
        "threads": thread_info,
        "garbage_collector": gc_info,
        "application": app_info,
        "network": network_info
    }

@app.get("/api/metrics", tags=["Metrics"], include_in_schema=False)
async def get_metrics():
    """Endpoint Prometheus-style pour le monitoring"""
    import psutil
    
    metrics = []
    
    cpu_percent = psutil.cpu_percent(interval=1)
    metrics.append(f"cpu_usage_percent {cpu_percent}")
    
    memory = psutil.virtual_memory()
    metrics.append(f"memory_total_bytes {memory.total}")
    metrics.append(f"memory_available_bytes {memory.available}")
    metrics.append(f"memory_used_bytes {memory.used}")
    metrics.append(f"memory_usage_percent {memory.percent}")
    
    disk = psutil.disk_usage('/')
    metrics.append(f"disk_total_bytes {disk.total}")
    metrics.append(f"disk_used_bytes {disk.used}")
    metrics.append(f"disk_free_bytes {disk.free}")
    metrics.append(f"disk_usage_percent {disk.percent}")
    
    process = psutil.Process()
    metrics.append(f"process_cpu_percent {process.cpu_percent()}")
    metrics.append(f"process_memory_rss_bytes {process.memory_info().rss}")
    metrics.append(f"process_memory_vms_bytes {process.memory_info().vms}")
    metrics.append(f"process_thread_count {process.num_threads()}")
    
    metrics.append(f"app_routers_loaded {len(loaded_routers)}")
    metrics.append(f"app_facebook_loaded {1 if facebook_loaded else 0}")
    metrics.append(f"app_facebook_routes {facebook_routes_count}")
    
    metrics.append(f"app_timestamp {int(datetime.now().timestamp())}")
    
    from fastapi.responses import Response
    return Response(
        content="\n".join(metrics),
        media_type="text/plain"
    )

@app.get("/api/ocr/status", tags=["OCR"], response_model=dict)
async def ocr_status():
    """Statut détaillé de l'intégration OCR/NLP"""
    status = {
        "ocr_integration": "active" if "ocr" in loaded_routers else "inactive",
        "nlp_integration": "active" if services_loaded.get("nlp") else "inactive",
        "timestamp": datetime.now().isoformat(),
        "endpoints": {}
    }
    
    if "ocr" in loaded_routers:
        prefix = loaded_routers.get('ocr', '/api/ocr')
        status["endpoints"] = {
            "health": f"{prefix}/health",
            "metrics": f"{prefix}/metrics",
            "auto_ocr": f"{prefix}/auto",
            "image_ocr": f"{prefix}/image",
            "pdf_ocr": f"{prefix}/pdf",
            "docx_ocr": f"{prefix}/docx",
            "excel_ocr": f"{prefix}/excel",
            "batch_ocr": f"{prefix}/batch",
            "text_processing": f"{prefix}/text",
            "form_extraction": f"{prefix}/form",
            "order_building": f"{prefix}/order"
        }
    
    return status

# ================================
#   MIDDLEWARE PERSONNALISÉ
# ================================
@app.middleware("http")
async def log_requests(request, call_next):
    """Middleware amélioré pour logger les requêtes"""
    import time
    from fastapi.responses import JSONResponse
    
    start_time = time.time()
    request_id = f"req_{int(start_time * 1000)}_{hash(request.url.path) % 10000}"
    
    logger.info(
        f"[{request_id}] IN  Method={request.method} "
        f"Path={request.url.path} "
        f"Client={request.client.host if request.client else 'unknown'} "
        f"User-Agent={request.headers.get('user-agent', 'unknown')}"
    )
    
    try:
        response = await call_next(request)
        process_time = (time.time() - start_time) * 1000
        
        logger.info(
            f"[{request_id}] OUT Status={response.status_code} "
            f"Duration={process_time:.2f}ms "
            f"Size={response.headers.get('content-length', 'unknown')}b"
        )
        
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = f"{process_time:.2f}ms"
        
        return response
        
    except Exception as exc:
        process_time = (time.time() - start_time) * 1000
        logger.error(
            f"[{request_id}] ERR Exception={exc.__class__.__name__} "
            f"Duration={process_time:.2f}ms "
            f"Error={str(exc)[:100]}"
        )
        raise

# ================================
#   GESTION DES ERREURS
# ================================
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Gestionnaire des exceptions HTTP"""
    logger.warning(
        f"HTTP Exception: {exc.status_code} - {exc.detail} "
        f"Path={request.url.path}"
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code,
            "path": request.url.path,
            "timestamp": datetime.now().isoformat(),
            "request_id": request.headers.get("X-Request-ID", "unknown")
        },
        headers={"X-Request-ID": request.headers.get("X-Request-ID", "unknown")}
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Gestionnaire des erreurs de validation"""
    logger.warning(
        f"Validation Error: {exc.errors()} "
        f"Path={request.url.path}"
    )
    
    return JSONResponse(
        status_code=422,
        content={
            "error": "Validation Error",
            "details": exc.errors(),
            "path": request.url.path,
            "timestamp": datetime.now().isoformat(),
            "request_id": request.headers.get("X-Request-ID", "unknown")
        },
        headers={"X-Request-ID": request.headers.get("X-Request-ID", "unknown")}
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Gestionnaire global des exceptions"""
    import traceback
    
    error_trace = traceback.format_exc()
    logger.error(
        f"Unhandled Exception: {exc.__class__.__name__} - {str(exc)} "
        f"Path={request.url.path}\n{error_trace}"
    )
    
    error_detail = str(exc) if os.getenv("ENVIRONMENT") == "development" else "Internal server error"
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": error_detail,
            "path": request.url.path,
            "timestamp": datetime.now().isoformat(),
            "request_id": request.headers.get("X-Request-ID", "unknown")
        },
        headers={"X-Request-ID": request.headers.get("X-Request-ID", "unknown")}
    )

# ================================
#   ÉVÉNEMENTS DE DÉMARRAGE/ARRÊT
# ================================
@app.on_event("startup")
async def startup_event():
    """Événement de démarrage de l'application"""
    logger.info("🚀 Application Live Commerce API démarrée")
    logger.info(f"📁 Répertoire: {current_dir}")
    logger.info(f"🌐 Environnement: {os.getenv('ENVIRONMENT', 'production')}")
    logger.info(f"🔗 URL Base: http://localhost:8000")
    
    global app_start_time
    app_start_time = datetime.now()
    logger.info(f"⏰ Heure de démarrage: {app_start_time.isoformat()}")

@app.on_event("shutdown")
async def shutdown_event():
    """Événement d'arrêt de l'application"""
    logger.info("🛑 Application Live Commerce API arrêtée")
    
    if services_loaded.get("facebook_graph"):
        try:
            from app.services.facebook_graph_api import FacebookGraphAPIService
            pass
        except:
            pass

# ================================
#   DÉMARRAGE
# ================================
print("\n" + "="*70)
print("🎯 LIVE COMMERCE API v3.0 - SYSTÈME COMPLET")
print("="*70)

print(f"\n📍 SYSTÈMES ACTIFS:")
print(f"   🔐 Authentication: /auth")
print(f"   🚚 Drivers:       /api/v1/drivers")
print(f"   🛒 Products:      /products")
print(f"   📦 Orders:        /api/v1/orders")
print(f"   🤖 Facebook Auto Reply: /api/v1/facebook/auto-reply")
print(f"   💬 Facebook Messenger: /api/v1/facebook/messenger")
print(f"   📱 Facebook:      /api/v1/facebook ({facebook_routes_count} routes)")

print(f"\n🆕 NOUVELLES FONCTIONNALITÉS COMMANDES:")
print(f"   • Création automatique depuis Facebook")
print(f"   • Gestion des statuts (pending, preparing, delivering, done)")
print(f"   • Items de commande avec produits")
print(f"   • Confirmation via Messenger")
print(f"   • Statistiques et rapports")
print(f"   • Filtrage et recherche avancée")

print(f"\n🆕 NOUVELLES FONCTIONNALITÉS FACEBOOK:")
print(f"   • Webhook Stream en temps réel")
print(f"   • Traitement NLP des commentaires")
print(f"   • Analytics live vidéo")
print(f"   • Gestion complète des messages")
print(f"   • Export des données")
print(f"   • Synchronisation périodique")
print(f"   • Notifications push")

print(f"\n🆕 NOUVELLES FONCTIONNALITÉS OCR/NLP:")
print(f"   • OCR Image, PDF, DOCX, Excel")
print(f"   • Détection automatique de langues")
print(f"   • Extraction de formulaires")
print(f"   • Construction automatique de commandes")
print(f"   • Traitement par lots (batch)")

print(f"\n🤖 NOUVELLES FONCTIONNALITÉS AUTO REPLY:")
print(f"   • Réponses automatiques IA")
print(f"   • Gestion intelligente des commentaires")
print(f"   • Analytics de performance")
print(f"   • Personnalisation des réponses")
print(f"   • Apprentissage automatique")

print(f"\n📊 SERVICES:")
for service, loaded in services_loaded.items():
    status = "✅" if loaded else "❌"
    print(f"   {status} {service.replace('_', ' ').title()}")

print(f"\n⭐ FONCTIONNALITÉS NOUVEAU SYSTÈME PRODUITS:")
print(f"   • Génération automatique code_article")
print(f"   • Gestion intelligente des catégories")
print(f"   • Filtrage multi-critères")
print(f"   • Statistiques vendeur")
print(f"   • Opérations en masse")

print(f"\n📚 DOCUMENTATION:")
print(f"   Swagger UI:  http://localhost:8000/docs")
print(f"   ReDoc:       http://localhost:8000/redoc")
print(f"   API Status:  http://localhost:8000/status")
print(f"   Facebook:    http://localhost:8000/api/facebook/status")

print(f"\n🔗 TEST RAPIDE:")
print(f"   Health:       curl http://localhost:8000/health")
print(f"   Status:       curl http://localhost:8000/status")
print(f"   Products:     curl http://localhost:8000/products/")
print(f"   Orders:       curl http://localhost:8000/api/v1/orders")
print(f"   Facebook Auto Reply: curl http://localhost:8000/api/v1/facebook/auto-reply")
print(f"   Facebook Messenger: curl http://localhost:8000/api/v1/facebook/messenger")
print(f"   System:       curl http://localhost:8000/api/system/debug")
print(f"   Metrics:      curl http://localhost:8000/api/metrics")

print(f"\n🔗 WEBHOOK FACEBOOK:")
print(f"   URL:          http://localhost:8000/api/v1/facebook/webhook")
print(f"   Subscribe:    curl -X POST http://localhost:8000/api/v1/facebook/webhook/subscribe")
print(f"   Stream:       curl http://localhost:8000/api/v1/facebook/webhook/stream")
print(f"   Health:       curl http://localhost:8000/api/v1/facebook/webhook/health")

print(f"\n🔗 ENDPOINTS OCR/NLP:")
if "ocr" in loaded_routers:
    prefix = loaded_routers.get('ocr', '/api/ocr')
    print(f"   Auto OCR:     curl -X POST http://localhost:8000{prefix}/auto")
    print(f"   Image OCR:    curl -X POST http://localhost:8000{prefix}/image")
    print(f"   PDF OCR:      curl -X POST http://localhost:8000{prefix}/pdf")
    print(f"   Form OCR:     curl -X POST http://localhost:8000{prefix}/form")
    print(f"   Batch OCR:    curl -X POST http://localhost:8000{prefix}/batch")

print("\n📊 LOGGING:")
print(f"   • Fichier de log: app.log")
print(f"   • Niveau: INFO")
print(f"   • Format: timestamp - module - level - message")
print(f"   • Request ID: Activé pour le tracing")

print("\n🔒 SÉCURITÉ:")
print(f"   • CORS configuré")
print(f"   • Middleware de logging")
print(f"   • Gestion d'erreurs centralisée")
print(f"   • Headers de sécurité")

print("\n" + "="*70)
print("✅ API DÉMARRÉE avec succès! Système complet opérationnel.")
print("="*70)

# Variable pour suivre l'uptime
app_start_time = datetime.now()

if __name__ == "__main__":
    uvicorn_config = {
        "app": "app.main:app",
        "host": "0.0.0.0",
        "port": 8000,
        "reload": os.getenv("ENVIRONMENT") == "development",
        "log_level": "info",
        "access_log": True,
        "workers": 4 if os.getenv("ENVIRONMENT") == "production" else 1,
        "proxy_headers": True,
        "forwarded_allow_ips": "*",
        "timeout_keep_alive": 30
    }
    
    logger.info(f"Lancement de l'application avec config: {uvicorn_config}")
    uvicorn.run(**uvicorn_config)