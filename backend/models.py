from datetime import datetime
from enum import StrEnum
from typing import Optional
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class Role(StrEnum):
    MANAGER = "manager"
    MEMBER = "member"


class PaymentMethod(StrEnum):
    WALLET = "wallet"
    UPI = "upi"
    BANK_TRANSFER = "bank_transfer"
    CASH = "cash"


class PaymentStatus(StrEnum):
    APPROVED = "approved"
    PENDING = "pending"
    REJECTED = "rejected"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(120))
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default=Role.MEMBER)
    wallet_balance: Mapped[int] = mapped_column(Integer, default=0)
    outstanding_due: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Settings(Base):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    apartment_name: Mapped[str] = mapped_column(String(160), default="Shraddhanjalli Apartment")
    monthly_fee: Mapped[int] = mapped_column(Integer, default=460)
    billing_month: Mapped[str] = mapped_column(String(40), default="November 2026")
    upi_id: Mapped[str] = mapped_column(String(160), default="")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    member_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    amount: Mapped[int] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(String(30))
    reference: Mapped[str] = mapped_column(String(180), default="")
    status: Mapped[str] = mapped_column(String(20), default=PaymentStatus.APPROVED)
    receipt_no: Mapped[Optional[str]] = mapped_column(String(40), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    approved_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)


class ApplicationState(Base):
    __tablename__ = "application_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AdditionalCost(Base):
    __tablename__ = "additional_costs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    amount: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(String(255))
    month_key: Mapped[str] = mapped_column(String(7), index=True)
    applied: Mapped[bool] = mapped_column(default=False)


class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    member_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    amount: Mapped[int] = mapped_column(Integer)
    transaction_type: Mapped[str] = mapped_column(String(20))
    note: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Receipt(Base):
    __tablename__ = "receipts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    payment_id: Mapped[str] = mapped_column(ForeignKey("payments.id"), unique=True)
    receipt_no: Mapped[str] = mapped_column(String(40), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
