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

## Manual server control

Run `python server_control.py` on the laptop. The control window has a
**SET UP DATABASE** button and one server button: green means the FastAPI server
and MariaDB are running and red means they are off.
Starting opens the local website and starts a free Cloudflare Quick Tunnel.
Stopping closes FastAPI and the tunnel; the public URL then becomes unavailable.
The control window must remain open while the server is running.

The setup action detects the operating system, starts Docker MariaDB when
available, otherwise detects or offers installation of MariaDB through the
system package manager. It then creates the configured database/user, seeds the
apartment records, and only starts FastAPI after port 3306 is ready.

A browser page cannot start a fully stopped server because no process is
listening for the click. The control window is therefore the server switch.

## Free public access with Cloudflare

When the server is started, the controller detects or offers to install
Cloudflare's free `cloudflared` tool using `winget`, then runs a Quick Tunnel
to the local FastAPI server. It displays a temporary HTTPS URL ending in
`trycloudflare.com`; click the URL in the controller to open it. The URL
changes when the tunnel restarts, and the laptop and controller must remain
running. No router port forwarding or paid domain is required.

The The FastAPI backend serves the frontend and MariaDB is the system of record. Login, dues, monthly billing, additional costs, payments, pending approvals, receipts, and settings are loaded from and saved to the authenticated API. Browser storage is only a local cache; it is not the authoritative data source. Direct UPI/bank submissions remain pending until the manager checks the bank statement and approves them because this free setup has no verified payment callback.

## Access from multiple home devices

The laptop is the server and must be connected to the same TP-Link Wi-Fi
network as the phones, tablets, and computers using the website. Start FastAPI
with the manual control window or directly:

```powershell
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Reserve the laptop's IPv4 address in the TP-Link router's **DHCP Address
Reservation** section. If the laptop receives `192.168.0.105`, every device on
the home network opens:

```text
http://192.168.0.105:8000
```

Configure Windows Firewall separately to allow TCP port 8000 on Private
networks. Do not enable router port forwarding for ports 8000 or 3306.

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
- Cash, bank transfer, and UPI payment methods
- Payment history and remaining-balance visibility
- Printable/downloadable payment receipts
- Self-service password changes in Settings
- Manager-controlled resident password resets in Settings
- Paper-style maintenance ledger printing from manager Settings
- Resident-facing Pay dues action
- Direct UPI/bank-reference submissions with manager approval
- Configurable apartment UPI ID and UPI-app payment link
- MariaDB-backed persistence through the FastAPI API

The current ledger has six residents, a ₹460 monthly fee, November 2026 as the operating month, and the confirmed dues. The app uses a new storage version so this clean starting state loads in the browser.

The browser UI requires the FastAPI server for login and database access. MariaDB stores the application state, while password credentials are stored as Argon2 hashes in the users table. If the API is unavailable, the UI reports the connection error instead of silently treating browser data as the live apartment account.

Residents sign in, open **Pay dues**, enter a full or partial amount, and choose UPI or Bank transfer. UPI and bank transfer are currently recorded with a payment reference for manager verification; no apartment convenience/platform fee is added. A bank or UPI provider may still apply its own external charges, which the apartment system cannot guarantee or control. A verified payment gateway should be connected before production use.

For direct UPI/bank payments, the manager first saves the apartment's public UPI ID in Settings. A resident can open the UPI app link, pay externally, enter the UTR/reference, and submit it. The item appears under **Payments awaiting approval**; the manager approves it after checking the bank/UPI notification, and only then is the resident's due reduced.

The removed wallet feature is not migrated or destructively deleted. Legacy MariaDB
tables and columns for wallet balances or wallet transactions may remain unused
in existing databases; the application no longer creates, reads, or updates them.
