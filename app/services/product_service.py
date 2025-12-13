# app/services/product_service.py - VERSION CORRIGÉE
from typing import Optional, List, Tuple, Dict, Any
from uuid import UUID
import logging
import re

from app.repositories.product import ProductRepository
from app.schemas.product_schemas import ProductCreate, ProductUpdate, ProductFilter
from app.models.product import Product

logger = logging.getLogger(__name__)

class ProductService:
    """Service pour la logique métier des produits"""
    
    def __init__(self, repository: ProductRepository):
        self.repository = repository
    
    def generate_product_code(self, category_name: str, seller_id: UUID) -> Dict[str, Any]:
        """Générer un code article unique"""
        try:
            # Nettoyer la catégorie
            clean_category = category_name.strip().upper()
            
            # Garder seulement les lettres
            letters = ''.join([c for c in clean_category if c.isalpha()])
            
            # Prendre les 3 premières lettres
            if len(letters) < 3:
                # Si moins de 3 lettres, compléter avec X
                prefix = letters.ljust(3, 'X')
            else:
                prefix = letters[:3].upper()
            
            # Récupérer le dernier numéro pour ce préfixe et vendeur
            max_number = self.repository.get_max_code_number(seller_id, prefix)
            next_number = max_number + 1
            
            # Formater le code (ex: VET001)
            code = f"{prefix}{next_number:03d}"
            
            logger.info(f"Généré code: {code} pour catégorie {category_name}, vendeur {seller_id}")
            return {"code": code, "next_number": next_number, "prefix": prefix}
            
        except Exception as e:
            logger.error(f"Erreur génération code: {e}")
            # Fallback
            prefix = "PRD"
            max_number = self.repository.get_max_code_number(seller_id, prefix)
            next_number = max_number + 1
            code = f"{prefix}{next_number:03d}"
            return {"code": code, "next_number": next_number, "prefix": prefix}
    
    def create_product(self, product_data: ProductCreate, seller_id: UUID) -> Product:
        """Créer un nouveau produit avec génération de code"""
        # Générer le code article
        code_info = self.generate_product_code(product_data.category_name, seller_id)
        
        # Préparer les données
        product_dict = product_data.model_dump()
        product_dict.update({
            "seller_id": seller_id,
            "code_article": code_info["code"],
            "category_name": product_data.category_name.strip().title()
        })
        
        # Créer le produit
        product = self.repository.create(product_dict)
        logger.info(f"Produit créé: {product.code_article} pour le vendeur {seller_id}")
        return product
    
    def get_product_by_id(self, product_id: UUID) -> Optional[Product]:
        """Récupérer un produit par ID"""
        return self.repository.get_by_id(product_id)
    
    def get_product_by_code(self, code_article: str) -> Optional[Product]:
        """Récupérer un produit par code article"""
        return self.repository.get_by_code(code_article)
    
    def update_product(
        self, 
        product_id: UUID, 
        seller_id: UUID,
        update_data: ProductUpdate
    ) -> Product:
        """Mettre à jour un produit avec vérification de propriété"""
        try:
            # Convertir seller_id en UUID si c'est une chaîne
            if isinstance(seller_id, str):
                seller_id = UUID(seller_id)
            
            # Vérifier que le produit existe et appartient au vendeur
            product = self.repository.get_by_id(product_id)
            if not product:
                raise ValueError("Produit non trouvé")
            
            # Vérifier l'appartenance
            if product.seller_id != seller_id:
                raise PermissionError(
                    f"Vous n'êtes pas autorisé à modifier ce produit. "
                    f"Produit: {product.seller_id}, Vendeur: {seller_id}"
                )
            
            update_dict = update_data.model_dump(exclude_unset=True)
            
            # Si la catégorie change, générer un nouveau code
            if 'category_name' in update_dict and update_dict['category_name'] != product.category_name:
                code_info = self.generate_product_code(update_dict['category_name'], seller_id)
                update_dict["code_article"] = code_info["code"]
                update_dict["category_name"] = update_dict['category_name'].strip().title()
            
            # Mettre à jour le produit
            updated_product = self.repository.update(product_id, update_dict)
            if not updated_product:
                raise ValueError("Échec de la mise à jour du produit")
            
            logger.info(f"Produit mis à jour: {updated_product.code_article}")
            return updated_product
            
        except PermissionError:
            raise
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Erreur update_product: {e}", exc_info=True)
            raise
    
    def delete_product(self, product_id: UUID, seller_id: UUID) -> bool:
        """Supprimer un produit"""
        try:
            # Convertir seller_id en UUID si c'est une chaîne
            if isinstance(seller_id, str):
                seller_id = UUID(seller_id)
            
            # Vérifier que le produit existe et appartient au vendeur
            product = self.repository.get_by_id(product_id)
            if not product:
                raise ValueError("Produit non trouvé")
            
            # Vérifier l'appartenance
            if product.seller_id != seller_id:
                raise PermissionError(
                    f"Vous n'êtes pas autorisé à supprimer ce produit. "
                    f"Produit: {product.seller_id}, Vendeur: {seller_id}"
                )
            
            # Supprimer le produit
            success = self.repository.delete(product_id)
            if not success:
                raise ValueError("Échec de la suppression du produit")
            
            logger.info(f"Produit supprimé: {product.code_article}")
            return True
            
        except PermissionError:
            raise
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Erreur delete_product: {e}", exc_info=True)
            raise
    
    def get_products_with_pagination(
        self,
        filter_params: ProductFilter,
        page: int = 1,
        size: int = 20,
        sort_by: str = "created_at",
        sort_desc: bool = True
    ) -> Tuple[List[Product], int]:
        """Récupérer les produits avec pagination"""
        skip = (page - 1) * size
        return self.repository.filter_products(
            filter_params=filter_params,
            skip=skip,
            limit=size,
            sort_by=sort_by,
            sort_desc=sort_desc
        )
    
    def search_products(self, search_term: str, limit: int = 20) -> List[Product]:
        """Rechercher des produits par texte (nom, description, catégorie)"""
        try:
            # Nettoyer le terme de recherche
            clean_search = search_term.strip()
            if len(clean_search) < 2:
                return []
            
            return self.repository.search_products(clean_search, limit)
        except Exception as e:
            logger.error(f"Erreur search_products: {e}")
            return []
    
    def filter_products(
        self,
        seller_id: Optional[UUID] = None,
        category_name: Optional[str] = None,
        is_active: Optional[bool] = None,
        price_min: Optional[float] = None,
        price_max: Optional[float] = None,
        search: Optional[str] = None,
        page: int = 1,
        size: int = 20,
        sort_by: str = "created_at",
        sort_desc: bool = True
    ) -> Tuple[List[Product], int]:
        """Filtrer les produits avec pagination (méthode complémentaire)"""
        try:
            # Créer les paramètres de filtre
            filter_params = ProductFilter(
                seller_id=seller_id,
                category_name=category_name,
                is_active=is_active,
                price_min=price_min,
                price_max=price_max,
                search=search
            )
            
            return self.get_products_with_pagination(
                filter_params=filter_params,
                page=page,
                size=size,
                sort_by=sort_by,
                sort_desc=sort_desc
            )
        except Exception as e:
            logger.error(f"Erreur filter_products: {e}")
            return [], 0
    
    def get_seller_categories(self, seller_id: UUID) -> List[str]:
        """Récupérer les catégories d'un vendeur"""
        try:
            # Convertir seller_id en UUID si c'est une chaîne
            if isinstance(seller_id, str):
                seller_id = UUID(seller_id)
            
            return self.repository.get_seller_categories(seller_id)
        except Exception as e:
            logger.error(f"Erreur get_seller_categories: {e}")
            return []
    
    def get_product_stats(self, seller_id: UUID) -> Dict[str, Any]:
        """Obtenir les statistiques des produits d'un vendeur"""
        try:
            # Convertir seller_id en UUID si c'est une chaîne
            if isinstance(seller_id, str):
                seller_id = UUID(seller_id)
            
            return self.repository.get_product_stats(seller_id)
        except Exception as e:
            logger.error(f"Erreur get_product_stats: {e}")
            # Retourner des stats vides en cas d'erreur
            return {
                "total_products": 0,
                "active_products": 0,
                "categories_count": 0,
                "total_stock": 0,
                "total_value": 0.0
            }
    
    def get_products_by_seller(self, seller_id: UUID, is_active: Optional[bool] = None) -> List[Product]:
        """Récupérer tous les produits d'un vendeur (méthode simplifiée)"""
        try:
            if isinstance(seller_id, str):
                seller_id = UUID(seller_id)
            
            # Utiliser le filtre avec pagination mais retourner tout
            filter_params = ProductFilter(seller_id=seller_id, is_active=is_active)
            products, total = self.get_products_with_pagination(
                filter_params=filter_params,
                page=1,
                size=1000,  # Grand nombre pour récupérer tout
                sort_by="created_at",
                sort_desc=True
            )
            
            return products
        except Exception as e:
            logger.error(f"Erreur get_products_by_seller: {e}")
            return []
    
    def validate_product_data(self, product_data: ProductCreate) -> List[str]:
        """Valider les données d'un produit"""
        errors = []
        
        # Valider le nom
        if not product_data.name or len(product_data.name.strip()) < 2:
            errors.append("Le nom du produit doit contenir au moins 2 caractères")
        
        # Valider la catégorie
        if not product_data.category_name or len(product_data.category_name.strip()) < 2:
            errors.append("La catégorie doit contenir au moins 2 caractères")
        
        # Valider le prix
        if product_data.price <= 0:
            errors.append("Le prix doit être supérieur à 0")
        
        # Valider le stock
        if product_data.stock < 0:
            errors.append("Le stock ne peut pas être négatif")
        
        return errors