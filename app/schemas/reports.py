# app/schemas/reports.py
from datetime import datetime
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, validator
from enum import Enum

# Enum pour les formats d'export
class ExportFormat(str, Enum):
    JSON = "json"
    CSV = "csv"
    PDF = "pdf"
    EXCEL = "excel"

# Enum pour les types de sections de rapport
class ReportSection(str, Enum):
    PRODUCTS = "products"
    FACEBOOK = "facebook"
    SALES = "sales"
    INVENTORY = "inventory"
    ENGAGEMENT = "engagement"

# Schéma pour la requête de rapport
class ReportRequest(BaseModel):
    sections: List[ReportSection] = Field(
        default_factory=lambda: [ReportSection.PRODUCTS, ReportSection.FACEBOOK],
        description="Sections à inclure dans le rapport"
    )
    start_date: Optional[datetime] = Field(
        None,
        description="Date de début de la période d'analyse"
    )
    end_date: Optional[datetime] = Field(
        None,
        description="Date de fin de la période d'analyse"
    )
    filters: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Filtres supplémentaires"
    )
    include_summary: bool = Field(
        True,
        description="Inclure un résumé exécutif"
    )
    include_charts: bool = Field(
        True,
        description="Inclure des données pour les graphiques"
    )
    
    @validator('end_date')
    def validate_dates(cls, v, values):
        if v and values.get('start_date'):
            if v < values['start_date']:
                raise ValueError("La date de fin doit être après la date de début")
        return v

# Schéma pour les statistiques de produits
class ProductStats(BaseModel):
    total: int = Field(0, description="Nombre total de produits")
    by_category: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Produits par catégorie"
    )
    stock_summary: Dict[str, Any] = Field(
        default_factory=dict,
        description="Résumé du stock"
    )
    price_summary: Dict[str, Any] = Field(
        default_factory=dict,
        description="Résumé des prix"
    )
    top_products: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Top produits par performance"
    )

# Schéma pour les données Facebook
class FacebookPageData(BaseModel):
    page_id: str
    page_name: str
    posts: int = Field(0, description="Nombre de posts")
    comments: int = Field(0, description="Nombre de commentaires")
    messages: int = Field(0, description="Nombre de messages")
    lives: int = Field(0, description="Nombre de lives")
    engagement: int = Field(0, description="Engagement total")
    top_post: Optional[Dict[str, Any]] = Field(
        None,
        description="Post avec le plus d'engagement"
    )
    fan_count: Optional[int] = Field(
        None,
        description="Nombre de fans de la page"
    )

class FacebookStats(BaseModel):
    pages: List[FacebookPageData] = Field(
        default_factory=list,
        description="Données par page"
    )
    total_engagement: int = Field(0, description="Engagement total")
    posts_summary: Dict[str, Any] = Field(
        default_factory=dict,
        description="Résumé des posts"
    )
    comments_summary: Dict[str, Any] = Field(
        default_factory=dict,
        description="Résumé des commentaires"
    )
    engagement_trend: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Tendance d'engagement sur la période"
    )

# Schéma pour les ventes
class SalesStats(BaseModel):
    total_orders: int = Field(0, description="Nombre total de commandes")
    total_revenue: float = Field(0.0, description="Revenu total")
    average_order_value: float = Field(0.0, description="Valeur moyenne des commandes")
    top_products: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Top produits vendus"
    )
    revenue_by_category: Dict[str, float] = Field(
        default_factory=dict,
        description="Revenu par catégorie"
    )
    conversion_rate: float = Field(0.0, description="Taux de conversion", ge=0, le=100)

# Schéma pour l'inventaire
class InventoryStats(BaseModel):
    total_stock_value: float = Field(0.0, description="Valeur totale du stock")
    stock_by_category: Dict[str, int] = Field(
        default_factory=dict,
        description="Stock par catégorie"
    )
    low_stock_items: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Articles avec stock faible"
    )
    out_of_stock_items: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Articles en rupture de stock"
    )
    turnover_rate: float = Field(0.0, description="Taux de rotation des stocks")

# Schéma pour l'engagement
class EngagementStats(BaseModel):
    total_interactions: int = Field(0, description="Nombre total d'interactions")
    engagement_rate: float = Field(0.0, description="Taux d'engagement", ge=0, le=100)
    top_performing_content: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Contenu le plus performant"
    )
    response_time: Dict[str, float] = Field(
        default_factory=dict,
        description="Temps de réponse moyen"
    )
    sentiment_analysis: Dict[str, float] = Field(
        default_factory=dict,
        description="Analyse de sentiment"
    )

# Schéma de réponse du rapport
class ReportResponse(BaseModel):
    report_id: str = Field(..., description="ID unique du rapport")
    generated_at: datetime = Field(..., description="Date et heure de génération")
    period_start: datetime = Field(..., description="Début de la période d'analyse")
    period_end: datetime = Field(..., description="Fin de la période d'analyse")
    sections: List[ReportSection] = Field(..., description="Sections incluses")
    
    # Données principales
    data: Dict[ReportSection, Any] = Field(
        default_factory=dict,
        description="Données du rapport par section"
    )
    
    # Résumé exécutif
    summary: Dict[str, Any] = Field(
        default_factory=dict,
        description="Résumé exécutif du rapport"
    )
    
    # Insights et recommandations
    insights: List[str] = Field(
        default_factory=list,
        description="Insights clés"
    )
    recommendations: List[str] = Field(
        default_factory=list,
        description="Recommandations"
    )
    
    # Métadonnées
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Métadonnées du rapport"
    )
    
    @validator('data')
    def validate_data_sections(cls, v, values):
        if 'sections' in values:
            for section in values['sections']:
                if section not in v:
                    v[section] = {}
        return v
    
    class Config:
        use_enum_values = True

# Schéma pour les rapports mensuels
class DailyStats(BaseModel):
    products: int = Field(0, description="Produits ajoutés")
    comments: int = Field(0, description="Commentaires Facebook")
    messages: int = Field(0, description="Messages Facebook")
    engagement: int = Field(0, description="Engagement total")
    
    class Config:
        from_attributes = True

class MonthlyReport(BaseModel):
    year: int
    month: int
    start_date: datetime
    end_date: datetime
    daily_stats: Dict[str, DailyStats] = Field(
        default_factory=dict,
        description="Statistiques quotidiennes"
    )
    monthly_summary: Dict[str, Any] = Field(
        default_factory=dict,
        description="Résumé mensuel"
    )
    comparisons: Dict[str, Any] = Field(
        default_factory=dict,
        description="Comparaisons avec le mois précédent"
    )
    
    class Config:
        from_attributes = True

# Schéma pour les options d'export
class ExportOptions(BaseModel):
    format: ExportFormat = Field(ExportFormat.JSON, description="Format d'export")
    report_type: str = Field("products", description="Type de rapport")
    start_date: Optional[datetime] = Field(None, description="Date de début")
    end_date: Optional[datetime] = Field(None, description="Date de fin")
    include_headers: bool = Field(True, description="Inclure les en-têtes")
    delimiter: str = Field(",", description="Délimiteur (pour CSV)")
    encoding: str = Field("utf-8", description="Encodage du fichier")

# Schéma pour la réponse d'export
class ExportResponse(BaseModel):
    success: bool
    format: str
    report_type: str
    period: Dict[str, str]
    generated_at: str
    download_url: Optional[str] = Field(
        None,
        description="URL de téléchargement du fichier"
    )
    file_size: Optional[int] = Field(
        None,
        description="Taille du fichier en octets"
    )
    data: Optional[Dict[str, Any]] = Field(
        None,
        description="Données (pour JSON)"
    )
    
    class Config:
        from_attributes = True

# Schéma pour les rapports programmés
class ScheduledReport(BaseModel):
    name: str = Field(..., max_length=100, description="Nom du rapport")
    frequency: str = Field(
        ...,
        pattern="^(daily|weekly|monthly|quarterly|yearly)$",
        description="Fréquence de génération"
    )
    sections: List[ReportSection]
    recipients: List[str] = Field(
        default_factory=list,
        description="Liste des emails des destinataires"
    )
    export_format: ExportFormat = Field(ExportFormat.PDF, description="Format d'export")
    include_summary: bool = Field(True, description="Inclure un résumé")
    active: bool = Field(True, description="Rapport actif")
    
    @validator('recipients')
    def validate_recipients(cls, v):
        if not v:
            raise ValueError("Au moins un destinataire est requis")
        return v

# Schéma pour les rapports historiques
class ReportHistory(BaseModel):
    report_id: str
    generated_at: datetime
    report_type: str
    period_start: datetime
    period_end: datetime
    sections: List[str]
    file_size: Optional[int]
    download_url: Optional[str]
    
    class Config:
        from_attributes = True