# Shraddhanjalli Apartment Maintenance Desk

A self-contained browser prototype for apartment maintenance accounts.

## Free local setup

The current deployment target is a local PC using MariaDB and FastAPI. No paid hosting or payment gateway is required.

1. Install Python and MariaDB locally.
2. Create a MariaDB database/user, or run `docker compose up -d mariadb` if Docker is already installed.
3. Copy `.env.example` to `.env` and set a long random `JWT_SECRET`.
4. Create a virtual environment and install `requirements.txt`.
5. Run `python -m backend.seed`.
6. Start the app with `uvicorn backend.main:app --reload`.
7. Open `http://127.0.0.1:8000`.

The FastAPI backend serves the frontend and stores authentication, dues, payments, wallets, and settings in MariaDB. Direct UPI/bank submissions remain pending until the manager checks the bank statement and approves them because this free setup has no verified payment callback. The current browser UI still uses its existing local demo storage; wiring each UI action to these API endpoints is the next integration phase.

## Run it

Open [index.html](./index.html) in a browser. No build step or installation is required.

Initial accounts:

- Manager: `Manager` / `Manager@2026`
- Residents use their username shown in Members and initial password `welcome1`.

## Included workflows

- Manager and resident sign-in profiles
- Member/unit directory with usernames and temporary passwords
- Monthly billing that adds the configured fee to each outstanding balance
- Carry-forward balances for late or partial payments
- Cash, bank transfer, UPI, and wallet payment methods
- Per-resident wallet balances and wallet top-ups
- Payment history and remaining-balance visibility
- Printable/downloadable payment receipts
- Self-service password changes in Settings
- Manager-controlled resident password resets in Settings
- Paper-style maintenance ledger printing from manager Settings
- Resident-facing Pay dues action using wallet funds
- Direct UPI/bank-reference submissions with manager approval
- Configurable apartment UPI ID and UPI-app payment link
- Browser persistence using `localStorage`

The current ledger has six residents, a ₹460 monthly fee, November 2026 as the operating month, and the confirmed dues. Resident wallets start at ₹0 and the manager wallet starts at ₹50,000. The app uses a new storage version so this clean starting state loads in the browser.

This version is a front-end prototype. Data is stored only in the current browser; a production deployment should replace `localStorage` with a secure server/database, hash passwords, and connect wallet top-ups to a verified payment provider.

Residents sign in, open **Pay dues**, enter a full or partial amount, and choose Wallet, UPI, or Bank transfer. UPI and bank transfer are currently recorded with a payment reference for manager verification; no apartment convenience/platform fee is added. A bank or UPI provider may still apply its own external charges, which the apartment system cannot guarantee or control. A verified payment gateway should be connected before production use.

For direct UPI/bank payments, the manager first saves the apartment's public UPI ID in Settings. A resident can open the UPI app link, pay externally, enter the UTR/reference, and submit it. The item appears under **Payments awaiting approval**; the manager approves it after checking the bank/UPI notification, and only then is the resident's due reduced.
