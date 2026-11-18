from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class PasswordReset(BaseModel):
    member_id: str
    new_password: str = Field(min_length=8)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class PaymentCreate(BaseModel):
    amount: int = Field(gt=0)
    method: str
    reference: str = ""


class SettingsUpdate(BaseModel):
    monthly_fee: int = Field(ge=0)
    billing_month: str = Field(min_length=1, max_length=40)
    upi_id: str = ""


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    username: str
    role: str
    outstanding_due: int


class PaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    member_id: str
    amount: int
    method: str
    reference: str
    status: str
    receipt_no: str | None
    created_at: datetime


class SettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    apartment_name: str
    monthly_fee: int
    billing_month: str
    upi_id: str
