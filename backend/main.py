from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import Base, engine, get_db
from .models import Payment, PaymentMethod, PaymentStatus, Role, Settings, User
from .schemas import LoginRequest, PaymentCreate, PaymentResponse, SettingsResponse, SettingsUpdate, TokenResponse, UserResponse
from .security import create_token, read_token, verify_password

settings = get_settings()
Base.metadata.create_all(bind=engine)
app = FastAPI(title="Shraddhanjalli Apartment API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
bearer = HTTPBearer()


def current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    try:
        user_id = read_token(credentials.credentials)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(error)) from error
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account not found")
    return user


def manager_only(user: User = Depends(current_user)) -> User:
    if user.role != Role.MANAGER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Manager access required")
    return user


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.username == payload.username))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    return TokenResponse(access_token=create_token(user.id))


@app.get("/api/me", response_model=UserResponse)
def me(user: User = Depends(current_user)) -> User:
    return user


@app.get("/api/members", response_model=list[UserResponse])
def members(_: User = Depends(manager_only), db: Session = Depends(get_db)) -> list[User]:
    return list(db.scalars(select(User).where(User.role == Role.MEMBER).order_by(User.name)))


@app.get("/api/settings", response_model=SettingsResponse)
def read_settings(_: User = Depends(current_user), db: Session = Depends(get_db)) -> Settings:
    settings_row = db.get(Settings, 1)
    if not settings_row:
        raise HTTPException(status_code=404, detail="Settings are not configured")
    return settings_row


@app.put("/api/settings", response_model=SettingsResponse)
def update_settings(payload: SettingsUpdate, _: User = Depends(manager_only), db: Session = Depends(get_db)) -> Settings:
    settings_row = db.get(Settings, 1) or Settings(id=1)
    settings_row.monthly_fee = payload.monthly_fee
    settings_row.billing_month = payload.billing_month
    settings_row.upi_id = payload.upi_id.strip()
    db.add(settings_row)
    db.commit()
    db.refresh(settings_row)
    return settings_row


@app.get("/api/payments", response_model=list[PaymentResponse])
def payments(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[Payment]:
    query = select(Payment).order_by(Payment.created_at.desc())
    if user.role != Role.MANAGER:
        query = query.where(Payment.member_id == user.id)
    return list(db.scalars(query))


@app.post("/api/payments", response_model=PaymentResponse)
def create_payment(payload: PaymentCreate, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Payment:
    valid_methods = {method.value for method in PaymentMethod}
    if payload.method not in valid_methods:
        raise HTTPException(status_code=400, detail="Unsupported payment method")
    if payload.amount > user.outstanding_due:
        raise HTTPException(status_code=400, detail="Payment exceeds outstanding due")
    if payload.method in {PaymentMethod.UPI.value, PaymentMethod.BANK_TRANSFER.value}:
        if not payload.reference.strip():
            raise HTTPException(status_code=400, detail="A UPI or bank reference is required")
        payment_status = PaymentStatus.PENDING.value
    else:
        if payload.method == PaymentMethod.WALLET.value and payload.amount > user.wallet_balance:
            raise HTTPException(status_code=400, detail="Insufficient wallet balance")
        user.outstanding_due -= payload.amount
        if payload.method == PaymentMethod.WALLET.value:
            user.wallet_balance -= payload.amount
        payment_status = PaymentStatus.APPROVED.value
    payment = Payment(member_id=user.id, amount=payload.amount, method=payload.method, reference=payload.reference.strip(), status=payment_status)
    if payment_status == PaymentStatus.APPROVED.value:
        payment.receipt_no = f"SA-{db.query(Payment).count() + 1:03d}"
        payment.approved_at = datetime.utcnow()
        payment.approved_by = user.id
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment


@app.post("/api/payments/{payment_id}/approve", response_model=PaymentResponse)
def approve_payment(payment_id: str, manager: User = Depends(manager_only), db: Session = Depends(get_db)) -> Payment:
    payment = db.get(Payment, payment_id)
    if not payment or payment.status != PaymentStatus.PENDING.value:
        raise HTTPException(status_code=404, detail="Pending payment not found")
    member = db.get(User, payment.member_id)
    if not member or payment.amount > member.outstanding_due:
        raise HTTPException(status_code=400, detail="Payment exceeds outstanding due")
    member.outstanding_due -= payment.amount
    payment.status = PaymentStatus.APPROVED.value
    payment.receipt_no = f"SA-{db.query(Payment).count():03d}"
    payment.approved_at = datetime.utcnow()
    payment.approved_by = manager.id
    db.commit()
    db.refresh(payment)
    return payment


@app.post("/api/payments/{payment_id}/reject", response_model=PaymentResponse)
def reject_payment(payment_id: str, _: User = Depends(manager_only), db: Session = Depends(get_db)) -> Payment:
    payment = db.get(Payment, payment_id)
    if not payment or payment.status != PaymentStatus.PENDING.value:
        raise HTTPException(status_code=404, detail="Pending payment not found")
    payment.status = PaymentStatus.REJECTED.value
    db.commit()
    db.refresh(payment)
    return payment


frontend_dir = Path(__file__).resolve().parents[1]
if (frontend_dir / "index.html").exists():
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
