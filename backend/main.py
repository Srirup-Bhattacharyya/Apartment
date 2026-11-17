from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import Base, engine, get_db
from .models import AdditionalCost, ApplicationState, Payment, PaymentMethod, PaymentStatus, Receipt, Role, Settings, User, WalletTransaction
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
    apply_server_billing(db)
    settings_row = db.get(Settings, 1)
    manager = db.scalar(select(User).where(User.role == Role.MANAGER))
    members = list(db.scalars(select(User).where(User.role == Role.MEMBER).order_by(User.name)))
    payments = list(db.scalars(select(Payment).order_by(Payment.created_at)))
    stored = db.get(ApplicationState, 1)
    payload = dict(stored.payload) if stored else {}
    if stored:
        existing_cost_ids = {item.id for item in db.scalars(select(AdditionalCost))}
        for item in payload.get("settings", {}).get("additionalCosts", []):
            if item.get("id") not in existing_cost_ids:
                db.add(AdditionalCost(
                    id=str(item["id"]),
                    amount=int(item.get("amount", 0)),
                    description=str(item.get("description", "")),
                    month_key=str(item.get("monthKey", "")),
                    applied=bool(item.get("applied", False)),
                ))
        existing_payment_ids = {item.id for item in db.scalars(select(Payment))}
        pending_ids = {item.get("id") for item in payload.get("pendingPayments", [])}
        for item in payload.get("payments", []) + payload.get("pendingPayments", []):
            if item.get("id") in existing_payment_ids:
                continue
            db.add(Payment(
                id=str(item["id"]),
                member_id=str(item["memberId"]),
                amount=int(item.get("amount", 0)),
                method=str(item.get("method", "")).lower().replace(" ", "_"),
                reference=str(item.get("note", "")),
                status=PaymentStatus.PENDING.value if item.get("id") in pending_ids else PaymentStatus.APPROVED.value,
                receipt_no=item.get("receiptNo") if item.get("id") not in pending_ids else None,
            ))
        existing_wallet_ids = {item.id for item in db.scalars(select(WalletTransaction))}
        for item in payload.get("walletTransactions", []):
            if item.get("id") not in existing_wallet_ids:
                db.add(WalletTransaction(
                    id=str(item["id"]),
                    member_id=str(item["memberId"]),
                    amount=int(item.get("amount", 0)),
                    transaction_type=str(item.get("type", "credit")),
                    note=str(item.get("note", "")),
                ))
        db.commit()
        for item in payload.get("payments", []):
            if item.get("receiptNo") and not db.scalar(select(Receipt).where(Receipt.payment_id == item.get("id"))):
                db.add(Receipt(id=f"receipt-{item['id']}", payment_id=item["id"], receipt_no=item["receiptNo"]))
        db.commit()
    payload["settings"] = {
        "monthlyFee": settings_row.monthly_fee if settings_row else 460,
        "apartmentName": settings_row.apartment_name if settings_row else "Shraddhanjalli Apartment",
        "billingMonth": settings_row.billing_month if settings_row else "November 2026",
        "upiId": settings_row.upi_id if settings_row else "",
        "additionalCosts": [
            {
                "id": item.id,
                "amount": item.amount,
                "description": item.description,
                "monthKey": item.month_key,
                "applied": item.applied,
            }
            for item in db.scalars(select(AdditionalCost).order_by(AdditionalCost.month_key, AdditionalCost.id))
        ],
    }
    if manager:
        payload["manager"] = {
            "id": manager.id,
            "name": manager.name,
            "username": manager.username,
            "role": manager.role,
            "wallet": manager.wallet_balance,
        }
    stored_members = {
        item.get("id"): item
        for item in payload.get("members", [])
        if isinstance(item, dict) and item.get("id")
    }
    payload["members"] = [
        {
            "id": member.id,
            "name": member.name,
            "unit": stored_members.get(member.id, {}).get("unit", ""),
            "username": member.username,
            "phone": stored_members.get(member.id, {}).get("phone", ""),
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
    payload["payments"] = database_payments
    payload["pendingPayments"] = database_pending_payments
    payload["walletTransactions"] = [
        {
            "id": item.id,
            "memberId": item.member_id,
            "amount": item.amount,
            "type": item.transaction_type,
            "note": item.note,
            "date": item.created_at.isoformat(),
        }
        for item in db.scalars(select(WalletTransaction).order_by(WalletTransaction.created_at))
    ]
    payload.setdefault("receipts", [])
    return payload


def month_number(label: str) -> int | None:
    try:
        month_name, year = label.split()
        month = datetime.strptime(month_name, "%B").month - 1
        return int(year) * 12 + month
    except (ValueError, IndexError):
        return None


def month_label(value: int) -> str:
    year, month = divmod(value, 12)
    return f"{datetime(year, month + 1, 1):%B} {year}"


def apply_server_billing(db: Session) -> None:
    settings_row = db.get(Settings, 1)
    if not settings_row:
        return
    current = datetime.utcnow()
    current_number = current.year * 12 + current.month - 1
    billed_number = month_number(settings_row.billing_month)
    if billed_number is None or current_number <= billed_number:
        return
    fee = settings_row.monthly_fee
    costs = list(db.scalars(select(AdditionalCost).where(AdditionalCost.applied.is_(False))))
    members = list(db.scalars(select(User).where(User.role == Role.MEMBER)))
    for number in range(billed_number + 1, current_number + 1):
        month_key = f"{number // 12:04d}-{number % 12 + 1:02d}"
        extra = sum(item.amount for item in costs if item.month_key == month_key)
        for member in members:
            member.outstanding_due += fee + extra
        for item in costs:
            if item.month_key == month_key:
                item.applied = True
    settings_row.billing_month = month_label(current_number)
    db.commit()


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
    stored_members = []
    for member_payload in payload.get("members", []):
        member = db.get(User, member_payload.get("id"))
        if not member:
            username = str(member_payload.get("username", "")).strip()
            password = str(member_payload.get("password", "")).strip()
            if not username or not password:
                raise HTTPException(status_code=400, detail="New members require a username and password")
            if db.scalar(select(User).where(User.username == username)):
                raise HTTPException(status_code=409, detail=f"Username already exists: {username}")
            member = User(
                id=str(member_payload.get("id") or ""),
                name=str(member_payload.get("name", "")).strip(),
                username=username,
                password_hash=hash_password(password),
                role=Role.MEMBER,
                outstanding_due=int(member_payload.get("due", 0)),
                wallet_balance=int(member_payload.get("wallet", 0)),
            )
            db.add(member)
        elif member.role == Role.MEMBER:
            member.name = str(member_payload.get("name", member.name)).strip()
            member.outstanding_due = int(member_payload.get("due", member.outstanding_due))
            member.wallet_balance = int(member_payload.get("wallet", member.wallet_balance))
        clean_member = dict(member_payload)
        clean_member.pop("password", None)
        stored_members.append(clean_member)
    manager_payload = payload.get("manager", {})
    manager = db.scalar(select(User).where(User.role == Role.MANAGER))
    if manager and "wallet" in manager_payload:
        manager.wallet_balance = int(manager_payload["wallet"])
    incoming_cost_ids = {str(item.get("id")) for item in settings_payload.get("additionalCosts", [])}
    for item in db.scalars(select(AdditionalCost)):
        if item.id not in incoming_cost_ids and not item.applied:
            db.delete(item)
    for item_payload in settings_payload.get("additionalCosts", []):
        item = db.get(AdditionalCost, item_payload.get("id"))
        if not item:
            item = AdditionalCost(id=str(item_payload["id"]))
        item.amount = int(item_payload.get("amount", 0))
        item.description = str(item_payload.get("description", "")).strip()
        item.month_key = str(item_payload.get("monthKey", ""))
        item.applied = bool(item_payload.get("applied", False))
        db.add(item)
    for item_payload in payload.get("walletTransactions", []):
        if not item_payload.get("id") or db.get(WalletTransaction, item_payload["id"]):
            continue
        db.add(WalletTransaction(
            id=str(item_payload["id"]),
            member_id=str(item_payload["memberId"]),
            amount=int(item_payload.get("amount", 0)),
            transaction_type=str(item_payload.get("type", "credit")),
            note=str(item_payload.get("note", "")),
        ))
    for item_payload in payload.get("payments", []) + payload.get("pendingPayments", []):
        payment_id = item_payload.get("id")
        if not payment_id or db.get(Payment, payment_id):
            continue
        status_value = PaymentStatus.PENDING.value if item_payload in payload.get("pendingPayments", []) else PaymentStatus.APPROVED.value
        payment = Payment(
            id=str(payment_id),
            member_id=str(item_payload["memberId"]),
            amount=int(item_payload.get("amount", 0)),
            method=str(item_payload.get("method", "")).lower().replace(" ", "_"),
            reference=str(item_payload.get("note", "")),
            status=status_value,
            receipt_no=item_payload.get("receiptNo") if status_value == PaymentStatus.APPROVED.value else None,
        )
        db.add(payment)
        if payment.receipt_no:
            db.add(Receipt(id=f"receipt-{payment.id}", payment_id=payment.id, receipt_no=payment.receipt_no))
    safe_payload = dict(payload)
    safe_payload["members"] = stored_members
    safe_payload.pop("manager", None)
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
