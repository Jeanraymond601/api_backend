from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from uuid import UUID
from datetime import datetime

class RegisterSchema(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)
    full_name: str = Field(..., min_length=1)  # ✅ Accepte full_name directement
    phone: Optional[str] = Field(None, min_length=8)  # ✅ Accepte "phone"
    role: str = Field("client", description="vendeur, livreur, client, admin")
    company_name: Optional[str] = None
    adresse: Optional[str] = None

    class Config:
        from_attributes = True

class UserResponse(BaseModel):
    id: UUID
    email: EmailStr
    full_name: Optional[str]
    telephone: Optional[str]
    role: Optional[str]
    adresse: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True

class LoginSchema(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)

class ForgotPasswordSchema(BaseModel):
    email: EmailStr

class VerifyResetCodeSchema(BaseModel):
    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6)

class ResetPasswordSchema(BaseModel):
    email: EmailStr
    reset_token: str
    new_password: str = Field(..., min_length=6)