from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import Base, engine, get_db
from .models import ApplicationState, Payment, PaymentMethod, PaymentStatus, Role, Settings, User
from .schemas import LoginRequest, PasswordChange, PasswordReset, PaymentCreate, PaymentResponse, SettingsResponse, SettingsUpdate, TokenResponse, UserResponse
from .security import create_token, hash_password, read_token, verify_password

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


def build_application_state(db: Session) -> dict:
    settings_row = db.get(Settings, 1)
    manager = db.scalar(select(User).where(User.role == Role.MANAGER))
    members = list(db.scalars(select(User).where(User.role == Role.MEMBER).order_by(User.name)))
    payments = list(db.scalars(select(Payment).order_by(Payment.created_at)))
    stored = db.get(ApplicationState, 1)
    payload = dict(stored.payload) if stored else {}
    payload["settings"] = {
        "monthlyFee": settings_row.monthly_fee if settings_row else 460,
        "apartmentName": settings_row.apartment_name if settings_row else "Shraddhanjalli Apartment",
        "billingMonth": settings_row.billing_month if settings_row else "November 2026",
        "upiId": settings_row.upi_id if settings_row else "",
        "additionalCosts": payload.get("settings", {}).get("additionalCosts", []),
    }
    if manager:
        payload["manager"] = {
            "id": manager.id,
            "name": manager.name,
            "username": manager.username,
            "role": manager.role,
            "wallet": manager.wallet_balance,
        }
    payload["members"] = [
        {
            "id": member.id,
            "name": member.name,
            "unit": "",
            "username": member.username,
            "phone": "",
            "due": member.outstanding_due,
            "wallet": member.wallet_balance,
        }
        for member in members
    ]
    database_payments = [
        {
            "id": payment.id,
            "memberId": payment.member_id,
            "amount": payment.amount,
            "method": payment.method,
            "date": payment.created_at.isoformat(),
            "note": payment.reference,
            "receiptNo": payment.receipt_no,
        }
        for payment in payments
        if payment.status == PaymentStatus.APPROVED.value
    ]
    database_pending_payments = [
        {
            "id": payment.id,
            "memberId": payment.member_id,
            "amount": payment.amount,
            "method": payment.method,
            "date": payment.created_at.isoformat(),
            "note": payment.reference,
        }
        for payment in payments
        if payment.status == PaymentStatus.PENDING.value
    ]
    payload["payments"] = payload.get("payments", database_payments)
    payload["pendingPayments"] = payload.get("pendingPayments", database_pending_payments)
    payload.setdefault("walletTransactions", [])
    payload.setdefault("receipts", [])
    return payload


@app.get("/api/state")
def read_application_state(_: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return build_application_state(db)


@app.put("/api/state")
def update_application_state(payload: dict, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    current_payload = build_application_state(db)
    if user.role != Role.MANAGER:
        incoming_members = payload.get("members", [])
        incoming_member = next((item for item in incoming_members if item.get("id") == user.id), None)
        current_member = next((item for item in current_payload["members"] if item.get("id") == user.id), None)
        if not incoming_member or not current_member:
            raise HTTPException(status_code=403, detail="Only your own account state can be updated")
        if payload.get("settings") != current_payload["settings"] or payload.get("manager") != current_payload["manager"]:
            raise HTTPException(status_code=403, detail="Manager settings cannot be changed by a resident")
        for item in incoming_members:
            if item.get("id") != user.id:
                matching = next((current for current in current_payload["members"] if current.get("id") == item.get("id")), None)
                if item != matching:
                    raise HTTPException(status_code=403, detail="Another resident account cannot be changed")
        for key in ("payments", "pendingPayments"):
            current_items = {item.get("id"): item for item in current_payload.get(key, [])}
            for item in payload.get(key, []):
                if item.get("id") in current_items:
                    if item != current_items[item.get("id")]:
                        raise HTTPException(status_code=403, detail="Existing payment records cannot be changed")
                elif item.get("memberId") != user.id:
                    raise HTTPException(status_code=403, detail="A resident can only add their own payment records")
        new_payments = [
            item for item in payload.get("payments", [])
            if item.get("id") not in {current.get("id") for current in current_payload.get("payments", [])}
        ]
        approved_amount = sum(int(item.get("amount", 0)) for item in new_payments)
        due_reduction = int(current_member["due"]) - int(incoming_member.get("due", current_member["due"]))
        wallet_reduction = int(current_member["wallet"]) - int(incoming_member.get("wallet", current_member["wallet"]))
        wallet_payment_amount = sum(
            int(item.get("amount", 0)) for item in new_payments if item.get("method") == PaymentMethod.WALLET.value
        )
        if due_reduction != approved_amount or wallet_reduction != wallet_payment_amount:
            raise HTTPException(status_code=400, detail="Resident payment changes do not match the balance changes")
        payload = dict(payload)
        payload["settings"] = current_payload["settings"]
        payload["manager"] = current_payload["manager"]
        payload["members"] = [
            incoming_member if item.get("id") == user.id else item
            for item in current_payload["members"]
        ]
    settings_payload = payload.get("settings", {})
    settings_row = db.get(Settings, 1) or Settings(id=1)
    settings_row.monthly_fee = int(settings_payload.get("monthlyFee", settings_row.monthly_fee))
    settings_row.billing_month = str(settings_payload.get("billingMonth", settings_row.billing_month))
    settings_row.apartment_name = str(settings_payload.get("apartmentName", settings_row.apartment_name))
    settings_row.upi_id = str(settings_payload.get("upiId", settings_row.upi_id)).strip()
    db.add(settings_row)
    for member_payload in payload.get("members", []):
        member = db.get(User, member_payload.get("id"))
        if member and member.role == Role.MEMBER:
            member.outstanding_due = int(member_payload.get("due", member.outstanding_due))
            member.wallet_balance = int(member_payload.get("wallet", member.wallet_balance))
    manager_payload = payload.get("manager", {})
    manager = db.scalar(select(User).where(User.role == Role.MANAGER))
    if manager and "wallet" in manager_payload:
        manager.wallet_balance = int(manager_payload["wallet"])
    safe_payload = dict(payload)
    safe_payload.pop("manager", None)
    safe_payload.pop("members", None)
    state_row = db.get(ApplicationState, 1) or ApplicationState(id=1)
    state_row.payload = safe_payload
    db.add(state_row)
    db.commit()
    return build_application_state(db)


@app.post("/api/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.username == payload.username))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    return TokenResponse(access_token=create_token(user.id))


@app.get("/api/me", response_model=UserResponse)
def me(user: User = Depends(current_user)) -> User:
    return user


@app.post("/api/auth/change-password")
def change_password(payload: PasswordChange, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, str]:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"status": "ok"}


@app.post("/api/auth/reset-password")
def reset_password(payload: PasswordReset, _: User = Depends(manager_only), db: Session = Depends(get_db)) -> dict[str, str]:
    member = db.get(User, payload.member_id)
    if not member or member.role != Role.MEMBER:
        raise HTTPException(status_code=404, detail="Resident account not found")
    member.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"status": "ok"}


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
