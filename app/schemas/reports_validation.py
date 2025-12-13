# app/schemas/reports_validation.py
from datetime import datetime
from typing import Dict, Any
from pydantic import BaseModel, validator

class ReportValidation(BaseModel):
    """Validations supplémentaires pour les rapports"""
    
    @classmethod
    def validate_date_range(cls, start_date: datetime, end_date: datetime) -> None:
        if start_date > end_date:
            raise ValueError("La date de début doit être avant la date de fin")
        
        # Limite de période (2 ans maximum)
        max_period = datetime.now().replace(year=datetime.now().year - 2)
        if start_date < max_period:
            raise ValueError("La période ne peut pas dépasser 2 ans dans le passé")
    
    @classmethod
    def validate_filters(cls, filters: Dict[str, Any]) -> None:
        allowed_filters = {
            'category', 'price_min', 'price_max', 'stock_min', 'stock_max',
            'engagement_min', 'engagement_max', 'sentiment', 'status'
        }
        
        for key in filters.keys():
            if key not in allowed_filters:
                raise ValueError(f"Filtre non autorisé: {key}")
    
    @classmethod
    def validate_export_data(cls, data: Dict[str, Any], format: str) -> None:
        if not data:
            raise ValueError("Aucune donnée à exporter")
        
        if format == 'csv' and not data.get('products'):
            raise ValueError("Export CSV nécessite des données de produits")