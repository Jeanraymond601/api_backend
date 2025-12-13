# app/repositories/product.py
from sqlalchemy.orm import Session
from sqlalchemy import Integer, func, and_, or_
from typing import Optional, List, Tuple, Dict, Any
from uuid import UUID
import logging

from app.models.product import Product
from app.schemas.product_schemas import ProductFilter

logger = logging.getLogger(__name__)

class ProductRepository:
    """Repository pour les opérations sur les produits"""
    
    def __init__(self, db: Session):
        self.db = db
    
    # ==================== CRUD OPERATIONS ====================
    
    def create(self, product_data: Dict[str, Any]) -> Product:
        """Créer un nouveau produit"""
        try:
            product = Product(**product_data)
            self.db.add(product)
            self.db.commit()
            self.db.refresh(product)
            logger.info(f"Produit créé: {product.code_article} (ID: {product.id})")
            return product
        except Exception as e:
            self.db.rollback()
            logger.error(f"Erreur création produit: {e}")
            raise
    
    def get_by_id(self, product_id: UUID) -> Optional[Product]:
        """Récupérer un produit par ID"""
        return self.db.query(Product).filter(Product.id == product_id).first()
    
    def get_by_code(self, code_article: str) -> Optional[Product]:
        """Récupérer un produit par code article"""
        return self.db.query(Product).filter(
            Product.code_article == code_article
        ).first()
    
    def update(self, product_id: UUID, update_data: Dict[str, Any]) -> Optional[Product]:
        """Mettre à jour un produit"""
        try:
            product = self.get_by_id(product_id)
            if not product:
                logger.warning(f"Produit non trouvé pour mise à jour: {product_id}")
                return None
            
            for field, value in update_data.items():
                if hasattr(product, field):
                    setattr(product, field, value)
            
            self.db.commit()
            self.db.refresh(product)
            logger.info(f"Produit mis à jour: {product.code_article}")
            return product
        except Exception as e:
            self.db.rollback()
            logger.error(f"Erreur mise à jour produit {product_id}: {e}")
            raise
    
    def delete(self, product_id: UUID) -> bool:
        """Supprimer un produit"""
        try:
            product = self.get_by_id(product_id)
            if not product:
                logger.warning(f"Produit non trouvé pour suppression: {product_id}")
                return False
            
            self.db.delete(product)
            self.db.commit()
            logger.info(f"Produit supprimé: {product.code_article} (ID: {product_id})")
            return True
        except Exception as e:
            self.db.rollback()
            logger.error(f"Erreur suppression produit {product_id}: {e}")
            raise
    
    # ==================== QUERY OPERATIONS ====================
    
    def get_by_seller_and_category(self, seller_id: UUID, category_name: str) -> List[Product]:
        """Récupérer les produits d'un vendeur pour une catégorie"""
        try:
            return self.db.query(Product).filter(
                Product.seller_id == seller_id,
                Product.category_name == category_name,
                Product.is_active == True
            ).all()
        except Exception as e:
            logger.error(f"Erreur get_by_seller_and_category: {e}")
            return []
    
    def count_by_seller_and_category(self, seller_id: UUID, category_name: str) -> int:
        """Compter les produits d'un vendeur dans une catégorie"""
        try:
            count = self.db.query(func.count(Product.id)).filter(
                Product.seller_id == seller_id,
                Product.category_name == category_name,
                Product.is_active == True
            ).scalar()
            return count or 0
        except Exception as e:
            logger.error(f"Erreur count_by_seller_and_category: {e}")
            return 0
    
    def get_max_code_number(self, seller_id: UUID, prefix: str) -> int:
        """Récupérer le numéro maximum pour un préfixe de code donné"""
        try:
            # Récupérer tous les codes du vendeur avec ce préfixe
            codes = self.db.query(Product.code_article).filter(
                Product.seller_id == seller_id,
                Product.code_article.like(f"{prefix}%")
            ).all()
            
            if not codes:
                return 0
            
            # Extraire les numéros
            numbers = []
            for code_tuple in codes:
                code = code_tuple[0]
                if code and code.startswith(prefix) and len(code) > len(prefix):
                    try:
                        # Extraire la partie numérique (après les 3 lettres)
                        num_part = code[len(prefix):]
                        # Supprimer les zéros non significatifs
                        num_part = num_part.lstrip('0') or '0'
                        if num_part.isdigit():
                            numbers.append(int(num_part))
                    except (ValueError, IndexError, TypeError) as e:
                        logger.warning(f"Erreur parsing code {code}: {e}")
                        continue
            
            return max(numbers) if numbers else 0
        except Exception as e:
            logger.error(f"Erreur get_max_code_number: {e}")
            return 0
    
    def filter_products(
        self, 
        filter_params: ProductFilter,
        skip: int = 0,
        limit: int = 100,
        sort_by: str = "created_at",
        sort_desc: bool = True
    ) -> Tuple[List[Product], int]:
        """Filtrer les produits avec pagination et tri"""
        try:
            query = self.db.query(Product)
            
            # Appliquer les filtres
            if filter_params.seller_id:
                query = query.filter(Product.seller_id == filter_params.seller_id)
            
            if filter_params.category_name:
                # Recherche insensible à la casse
                query = query.filter(
                    func.lower(Product.category_name).contains(
                        func.lower(filter_params.category_name)
                    )
                )
            
            if filter_params.is_active is not None:
                query = query.filter(Product.is_active == filter_params.is_active)
            
            if filter_params.price_min is not None:
                query = query.filter(Product.price >= filter_params.price_min)
            
            if filter_params.price_max is not None:
                query = query.filter(Product.price <= filter_params.price_max)
            
            if filter_params.search:
                search_term = f"%{filter_params.search}%"
                query = query.filter(
                    or_(
                        Product.name.ilike(search_term),
                        Product.description.ilike(search_term),
                        Product.category_name.ilike(search_term)
                    )
                )
            
            # Compter le total AVANT pagination
            total = query.count()
            
            # Appliquer le tri
            valid_sort_columns = ['name', 'price', 'stock', 'created_at', 'updated_at']
            if sort_by in valid_sort_columns and hasattr(Product, sort_by):
                sort_column = getattr(Product, sort_by)
                if sort_desc:
                    query = query.order_by(sort_column.desc())
                else:
                    query = query.order_by(sort_column.asc())
            else:
                # Tri par défaut
                query = query.order_by(Product.created_at.desc())
            
            # Appliquer la pagination
            if limit > 0:
                query = query.offset(skip).limit(limit)
            
            products = query.all()
            logger.debug(f"filter_products: {len(products)} produits trouvés sur {total}")
            return products, total
            
        except Exception as e:
            logger.error(f"Erreur filter_products: {e}")
            return [], 0
    
    def search_products(self, search_term: str, limit: int = 20) -> List[Product]:
        """Rechercher des produits par texte"""
        try:
            if not search_term or len(search_term.strip()) < 2:
                return []
            
            term = f"%{search_term.strip()}%"
            return self.db.query(Product).filter(
                and_(
                    Product.is_active == True,
                    or_(
                        Product.name.ilike(term),
                        Product.description.ilike(term),
                        Product.category_name.ilike(term),
                        Product.code_article.ilike(term)
                    )
                )
            ).limit(limit).all()
        except Exception as e:
            logger.error(f"Erreur search_products: {e}")
            return []
    
    def get_seller_categories(self, seller_id: UUID) -> List[str]:
        """Récupérer les catégories d'un vendeur"""
        try:
            categories = self.db.query(
                func.distinct(Product.category_name)
            ).filter(
                Product.seller_id == seller_id,
                Product.is_active == True,
                Product.category_name.isnot(None)
            ).order_by(Product.category_name).all()
            
            return [cat[0] for cat in categories if cat[0]]
        except Exception as e:
            logger.error(f"Erreur get_seller_categories: {e}")
            return []
    
    def get_product_stats(self, seller_id: UUID) -> Dict[str, Any]:
        """Obtenir les statistiques des produits d'un vendeur"""
        try:
            stats = self.db.query(
                func.count(Product.id).label('total_products'),
                func.sum(func.cast(Product.is_active, Integer)).label('active_products'),
                func.count(func.distinct(Product.category_name)).label('categories_count'),
                func.coalesce(func.sum(Product.stock), 0).label('total_stock'),
                func.coalesce(func.sum(Product.price * Product.stock), 0).label('total_value')
            ).filter(
                Product.seller_id == seller_id
            ).first()
            
            if not stats:
                return self._empty_stats()
            
            return {
                'total_products': stats.total_products or 0,
                'active_products': stats.active_products or 0,
                'categories_count': stats.categories_count or 0,
                'total_stock': int(stats.total_stock or 0),
                'total_value': float(stats.total_value or 0.0)
            }
        except Exception as e:
            logger.error(f"Erreur get_product_stats: {e}")
            return self._empty_stats()
    
    def _empty_stats(self) -> Dict[str, Any]:
        """Retourner des statistiques vides"""
        return {
            'total_products': 0,
            'active_products': 0,
            'categories_count': 0,
            'total_stock': 0,
            'total_value': 0.0
        }
    
    def get_all_active_products(self, seller_id: Optional[UUID] = None) -> List[Product]:
        """Récupérer tous les produits actifs (optionnellement pour un vendeur)"""
        try:
            query = self.db.query(Product).filter(Product.is_active == True)
            if seller_id:
                query = query.filter(Product.seller_id == seller_id)
            return query.all()
        except Exception as e:
            logger.error(f"Erreur get_all_active_products: {e}")
            return []
    
    def get_products_by_seller(self, seller_id: UUID, only_active: bool = True) -> List[Product]:
        """Récupérer tous les produits d'un vendeur"""
        try:
            query = self.db.query(Product).filter(Product.seller_id == seller_id)
            if only_active:
                query = query.filter(Product.is_active == True)
            return query.order_by(Product.created_at.desc()).all()
        except Exception as e:
            logger.error(f"Erreur get_products_by_seller: {e}")
            return []