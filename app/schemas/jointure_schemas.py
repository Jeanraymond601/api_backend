from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import uuid

class VendeurAvecDetails(BaseModel):
    user_id: uuid.UUID
    full_name: str
    email: str
    telephone: Optional[str]
    adresse: Optional[str]
    statut: str
    created_at: datetime
    company_name: str
    abonnement_type: str
    abonnement_status: str

class SellerWithUserResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    company_name: str
    facebook_page: Optional[str]
    abonnement_type: str
    abonnement_status: str
    created_at: datetime
    
    # User info
    user: 'UserForJointure'
    
    class Config:
        from_attributes = True

class UserForJointure(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str
    telephone: Optional[str]
    adresse: Optional[str]
    role: str
    statut: str
    created_at: datetime

# Résoudre les références circulaires
SellerWithUserResponse.update_forward_refs()