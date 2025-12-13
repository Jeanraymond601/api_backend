# app/routers/product.py - VERSION AVEC ORDRE CORRECT
from fastapi import APIRouter, Depends, HTTPException, status, Query, Path, Request
from typing import Optional, List, Union
from uuid import UUID
import traceback
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_seller, get_db, get_current_user, resolve_identifier_to_seller_id
from app.schemas.product_schemas import (
    ProductCreate, ProductUpdate, ProductResponse, 
    ProductFilter, ProductListResponse, CodeGenerationRequest, 
    CodeGenerationResponse, ProductStats
)
from app.services.product_service import ProductService
from app.repositories.product import ProductRepository

router = APIRouter(prefix="/products", tags=["products"])

# ==================== HELPER FUNCTIONS ====================

def get_product_service(db: Session = Depends(get_db)) -> ProductService:
    repo = ProductRepository(db)
    return ProductService(repo)

# ==================== ENDPOINTS SPÉCIFIQUES (EN PREMIER !) ====================

@router.get("/search", 
    response_model=List[ProductResponse],
    summary="Recherche texte dans les produits"
)
async def search_products(
    q: str = Query(..., min_length=2, description="Terme de recherche"),
    limit: int = Query(20, ge=1, le=100, description="Nombre maximum de résultats"),
    service: ProductService = Depends(get_product_service)
):
    """Rechercher des produits par texte"""
    try:
        print(f"\n🔍 GET /products/search?q={q}")
        products = service.search_products(search_term=q, limit=limit)
        print(f"✅ {len(products)} résultats trouvés")
        return products
    except Exception as e:
        print(f"❌ Erreur recherche: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la recherche: {str(e)}"
        )

@router.get("/filter", 
    response_model=ProductListResponse,
    summary="Filtrer les produits"
)
async def filter_products(
    seller_id: Optional[UUID] = Query(None, description="ID du vendeur"),
    category_name: Optional[str] = Query(None, description="Nom de la catégorie"),
    is_active: Optional[bool] = Query(None, description="Statut actif"),
    price_min: Optional[float] = Query(None, ge=0, description="Prix minimum"),
    price_max: Optional[float] = Query(None, ge=0, description="Prix maximum"),
    search: Optional[str] = Query(None, description="Recherche texte (nom, description, catégorie)"),
    page: int = Query(1, ge=1, description="Numéro de page"),
    size: int = Query(20, ge=1, le=100, description="Taille de la page"),
    sort_by: str = Query("created_at", description="Champ de tri"),
    sort_desc: bool = Query(True, description="Tri décroissant"),
    service: ProductService = Depends(get_product_service)
):
    """Filtrer les produits avec pagination"""
    try:
        print(f"\n⚙️ GET /products/filter")
        print(f"   seller_id: {seller_id}, category: {category_name}")
        
        # Construire les paramètres de filtre
        filter_params = ProductFilter(
            seller_id=seller_id,
            category_name=category_name,
            is_active=is_active,
            price_min=price_min,
            price_max=price_max,
            search=search
        )
        
        # Récupérer les produits avec pagination
        products, total = service.get_products_with_pagination(
            filter_params=filter_params,
            page=page,
            size=size,
            sort_by=sort_by,
            sort_desc=sort_desc
        )
        
        # Calculer le nombre de pages
        pages = (total + size - 1) // size if size > 0 else 1
        
        print(f"✅ {len(products)} produits sur {total} (page {page}/{pages})")
        
        return ProductListResponse(
            items=products,
            total=total,
            page=page,
            size=size,
            pages=pages
        )
    except ValueError as e:
        print(f"❌ Erreur validation: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        print(f"❌ Erreur filtrage: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors du filtrage des produits: {str(e)}"
        )

@router.post("/generate-code", 
    response_model=CodeGenerationResponse,
    summary="Générer un code article"
)
async def generate_product_code(
    request: CodeGenerationRequest,
    service: ProductService = Depends(get_product_service)
):
    """Générer un code article pour tester la logique"""
    try:
        print(f"\n🔢 POST /products/generate-code")
        print(f"   Catégorie: {request.category_name}")
        print(f"   Seller: {request.seller_id}")
        
        code_info = service.generate_product_code(
            category_name=request.category_name,
            seller_id=request.seller_id
        )
        
        print(f"✅ Code généré: {code_info['code']}")
        
        return CodeGenerationResponse(
            category_name=request.category_name,
            seller_id=request.seller_id,
            generated_code=code_info["code"],
            next_number=code_info["next_number"]
        )
    except Exception as e:
        print(f"❌ Erreur génération: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la génération du code: {str(e)}"
        )

# ==================== ENDPOINTS DE DEBUG (EN PREMIER AUSSI) ====================

@router.get("/debug/current-seller")
async def debug_current_seller(
    current_seller: dict = Depends(get_current_seller)
):
    """Endpoint de debug pour voir les infos du vendeur"""
    print(f"\n🔧 DEBUG Current Seller:")
    for key, value in current_seller.items():
        print(f"   {key}: {value}")
    
    return {
        "message": "Informations du vendeur connecté",
        "seller_info": current_seller,
        "has_seller_id": "seller_id" in current_seller,
        "has_id": "id" in current_seller,
        "has_user_id": "user_id" in current_seller
    }

@router.get("/test/resolve/{identifier}")
async def test_resolve_identifier(
    identifier: str,
    db: Session = Depends(get_db)
):
    """Endpoint de test pour la résolution d'identifiant"""
    try:
        seller_id = resolve_identifier_to_seller_id(identifier, db)
        return {
            "input": identifier,
            "resolved_seller_id": str(seller_id),
            "message": "✅ Résolution réussie"
        }
    except Exception as e:
        return {
            "input": identifier,
            "error": str(e),
            "message": "❌ Échec de résolution"
        }

# ==================== ENDPOINT POUR LE VENDEUR CONNECTÉ ====================

@router.get("/my-products", 
    response_model=List[ProductResponse],
    summary="Lister les produits du vendeur connecté"
)
async def get_my_products(
    current_seller: dict = Depends(get_current_seller),
    is_active: Optional[bool] = Query(None, description="Filtrer par statut actif"),
    page: int = Query(1, ge=1, description="Numéro de page"),
    size: int = Query(20, ge=1, le=100, description="Taille de la page"),
    service: ProductService = Depends(get_product_service)
):
    try:
        print(f"\n📥 GET /products/my-products")
        
        seller_id = current_seller.get("seller_id") or current_seller.get("id")
        
        print(f"👤 Vendeur connecté: {current_seller.get('company_name')}")
        print(f"🔍 seller_id: {seller_id}")
        
        if not seller_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Impossible de déterminer le vendeur"
            )
        
        filter_params = ProductFilter(seller_id=seller_id, is_active=is_active)
        products, _ = service.get_products_with_pagination(
            filter_params=filter_params,
            page=page,
            size=size,
            sort_by="created_at",
            sort_desc=True
        )
        
        print(f"✅ {len(products)} produits trouvés")
        return products
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Erreur: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération des produits: {str(e)}"
        )

# ==================== ENDPOINT PRINCIPAL CORRIGÉ ====================

@router.get("/seller/{identifier}", 
    response_model=List[ProductResponse],
    summary="Lister les produits d'un vendeur",
    description="Accepte soit seller_id (UUID de la table sellers) soit user_id (UUID de la table users)"
)
async def get_products_by_seller(
    request: Request,
    identifier: str = Path(..., description="ID du vendeur (seller_id) ou ID utilisateur (user_id)"),
    is_active: Optional[bool] = Query(None, description="Filtrer par statut actif"),
    page: int = Query(1, ge=1, description="Numéro de page"),
    size: int = Query(20, ge=1, le=100, description="Taille de la page"),
    sort_by: str = Query("created_at", description="Champ de tri"),
    sort_desc: bool = Query(True, description="Tri décroissant"),
    service: ProductService = Depends(get_product_service),
    db: Session = Depends(get_db)
):
    try:
        print(f"\n📥 GET /products/seller/{identifier}")
        print(f"   Identifiant reçu: {identifier}")
        
        # Résoudre l'identifiant en seller_id valide
        seller_id = resolve_identifier_to_seller_id(identifier, db)
        print(f"✅ Identifiant résolu en seller_id: {seller_id}")
        
        # Filtrer les produits
        filter_params = ProductFilter(seller_id=seller_id, is_active=is_active)
        products, _ = service.get_products_with_pagination(
            filter_params=filter_params,
            page=page,
            size=size,
            sort_by=sort_by,
            sort_desc=sort_desc
        )
        
        print(f"✅ {len(products)} produits trouvés pour seller: {seller_id}")
        return products
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Erreur: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération des produits: {str(e)}"
        )

# ==================== STATISTIQUES ET CATÉGORIES ====================

@router.get("/seller/{identifier}/stats", 
    response_model=ProductStats
)
async def get_seller_product_stats(
    identifier: str,
    service: ProductService = Depends(get_product_service),
    db: Session = Depends(get_db)
):
    try:
        print(f"\n📊 GET /products/seller/{identifier}/stats")
        
        seller_id = resolve_identifier_to_seller_id(identifier, db)
        
        stats = service.get_product_stats(seller_id)
        print(f"✅ Stats trouvées pour seller: {seller_id}")
        return stats
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors du calcul des statistiques: {str(e)}"
        )

@router.get("/seller/{identifier}/categories", 
    response_model=List[str]
)
async def get_seller_categories(
    identifier: str,
    service: ProductService = Depends(get_product_service),
    db: Session = Depends(get_db)
):
    try:
        print(f"\n🗂️ GET /products/seller/{identifier}/categories")
        
        seller_id = resolve_identifier_to_seller_id(identifier, db)
        
        categories = service.get_seller_categories(seller_id)
        print(f"✅ {len(categories)} catégories trouvées")
        return categories
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération des catégories: {str(e)}"
        )

# ==================== CRUD ENDPOINTS (EN DERNIER !) ====================

@router.post("/", 
    response_model=ProductResponse, 
    status_code=status.HTTP_201_CREATED
)
async def create_product(
    product_data: ProductCreate,
    current_seller: dict = Depends(get_current_seller),
    service: ProductService = Depends(get_product_service)
):
    try:
        print(f"\n📨 POST /products/")
        
        seller_id = current_seller.get("seller_id") or current_seller.get("id")
        
        if not seller_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Impossible de déterminer le vendeur"
            )
        
        print(f"👤 Vendeur: {current_seller.get('company_name')}")
        print(f"🔍 seller_id: {seller_id}")
        
        product = service.create_product(
            product_data=product_data,
            seller_id=seller_id
        )
        
        print(f"✅ Produit créé: {product.id}")
        return product
        
    except HTTPException:
        raise
    except ValueError as e:
        print(f"❌ Erreur validation: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        print(f"❌ Erreur inattendue: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la création du produit: {str(e)}"
        )

@router.get("/{product_id}", 
    response_model=ProductResponse
)
async def get_product_by_id(
    product_id: UUID,
    current_seller: dict = Depends(get_current_seller),
    service: ProductService = Depends(get_product_service)
):
    try:
        print(f"\n📥 GET /products/{product_id}")
        
        product = service.get_product_by_id(product_id)
        
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Produit non trouvé"
            )
        
        seller_id = current_seller.get("seller_id") or current_seller.get("id")
        if str(product.seller_id) != str(seller_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vous n'avez pas accès à ce produit"
            )
        
        print(f"✅ Produit trouvé: {product.name}")
        return product
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Erreur: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération du produit: {str(e)}"
        )

@router.patch("/{product_id}", 
    response_model=ProductResponse
)
async def update_product(
    product_id: UUID,
    product_update: ProductUpdate,
    current_seller: dict = Depends(get_current_seller),
    service: ProductService = Depends(get_product_service)
):
    try:
        print(f"\n🔄 PATCH /products/{product_id}")
        
        seller_id = current_seller.get("seller_id") or current_seller.get("id")
        
        print(f"👤 Vendeur: {current_seller.get('company_name')}")
        print(f"🔍 seller_id: {seller_id}")
        
        product = service.update_product(
            product_id=product_id,
            seller_id=seller_id,
            update_data=product_update
        )
        
        print(f"✅ Produit mis à jour: {product.name}")
        return product
        
    except ValueError as e:
        print(f"❌ Erreur validation: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except PermissionError as e:
        print(f"❌ Erreur permission: {e}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        print(f"❌ Erreur inattendue: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la mise à jour du produit: {str(e)}"
        )

@router.delete("/{product_id}", 
    status_code=status.HTTP_204_NO_CONTENT
)
async def delete_product(
    product_id: UUID,
    current_seller: dict = Depends(get_current_seller),
    service: ProductService = Depends(get_product_service)
):
    try:
        print(f"\n🗑️ DELETE /products/{product_id}")
        
        seller_id = current_seller.get("seller_id") or current_seller.get("id")
        
        print(f"👤 Vendeur: {current_seller.get('company_name')}")
        print(f"🔍 seller_id: {seller_id}")
        
        service.delete_product(product_id=product_id, seller_id=seller_id)
        
        print(f"✅ Produit supprimé: {product_id}")
        return None
        
    except ValueError as e:
        print(f"❌ Erreur validation: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except PermissionError as e:
        print(f"❌ Erreur permission: {e}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        print(f"❌ Erreur inattendue: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la suppression du produit: {str(e)}"
        )