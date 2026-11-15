import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from tkinter import messagebox, simpledialog
from urllib.parse import unquote

from sqlalchemy.engine import make_url


PROJECT_ROOT = Path(__file__).resolve().parent
DATABASE_PORT = 3306
IDENTIFIER = re.compile(r"^[A-Za-z0-9_]+$")


def _database_url():
    from backend.config import get_settings

    return make_url(get_settings().database_url)


def _port_open() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        connection.settimeout(1)
        return connection.connect_ex(("127.0.0.1", DATABASE_PORT)) == 0


def _run(command: list[str], *, cwd: Path = PROJECT_ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)


def _mariadb_program(name: str) -> Path | None:
    candidates = list(Path("C:/Program Files").glob("MariaDB*/bin/" + name))
    return next((candidate for candidate in candidates if candidate.exists()), None)


def _initialize_windows_service() -> tuple[bool, str]:
    installer = _mariadb_program("mariadb-install-db.exe")
    if installer is None:
        return False, "MariaDB is installed, but mariadb-install-db.exe was not found."
    root_password = simpledialog.askstring("MariaDB setup", "Create a MariaDB root password:", show="*")
    if root_password is None or not root_password:
        return False, "A MariaDB root password is required."
    data_directory = PROJECT_ROOT / "database"
    result = _run(
        [
            str(installer),
            f"--datadir={data_directory}",
            "--service=ShraddhanjalliMariaDB",
            f"--password={root_password}",
        ]
    )
    if result.returncode != 0:
        return False, result.stderr.strip() or result.stdout.strip() or "MariaDB database initialization failed."
    return True, ""


def _start_local_service() -> tuple[bool, str]:
    system = platform.system()
    if system == "Windows":
        services = _run(
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                "Get-Service | Where-Object { $_.Name -match 'MariaDB|MySQL' } | Select-Object -ExpandProperty Name",
            ]
        )
        service_names = [line.strip() for line in services.stdout.splitlines() if line.strip()]
        if not service_names:
            initialized, initialization_error = _initialize_windows_service()
            if not initialized:
                return False, initialization_error or "No MariaDB/MySQL Windows service was found."
            service_names = ["ShraddhanjalliMariaDB"]
        errors = []
        for service in service_names:
            result = _run(["sc.exe", "start", service])
            if result.returncode == 0 or "already been started" in result.stdout.lower():
                return True, ""
            errors.append(result.stderr.strip() or result.stdout.strip() or f"Could not start service {service}.")
        return False, " ".join(errors)
    if system == "Darwin":
        result = _run(["brew", "services", "start", "mariadb"])
        return result.returncode == 0, result.stderr.strip()
    result = _run(["sudo", "systemctl", "start", "mariadb"])
    return result.returncode == 0, result.stderr.strip()


def _install_database() -> str:
    system = platform.system()
    if system == "Windows" and shutil.which("winget"):
        installed = _run(["winget", "list", "--id", "MariaDB.Server", "--exact"])
        if installed.returncode == 0 and "MariaDB" in installed.stdout:
            return ""
        result = _run(["winget", "install", "--id", "MariaDB.Server", "--exact", "--accept-source-agreements", "--accept-package-agreements"])
    elif system == "Darwin" and shutil.which("brew"):
        result = _run(["brew", "install", "mariadb"])
    elif system == "Linux" and shutil.which("apt-get"):
        result = _run(["sudo", "apt-get", "update"])
        if result.returncode == 0:
            result = _run(["sudo", "apt-get", "install", "-y", "mariadb-server"])
    else:
        return "No supported package manager was found. Install MariaDB Server manually."
    if result.returncode != 0:
        return result.stderr.strip() or result.stdout.strip() or "The MariaDB installation command failed."
    return ""


def _configure_database() -> str:
    url = _database_url()
    database = url.database or ""
    username = url.username or ""
    password = unquote(url.password or "")
    if not IDENTIFIER.fullmatch(database) or not IDENTIFIER.fullmatch(username):
        return "DATABASE_URL contains an unsupported database or username."
    try:
        import pymysql
    except ImportError:
        return "PyMySQL is missing. Install the project requirements first."

    try:
        connection = pymysql.connect(host="127.0.0.1", port=DATABASE_PORT, user=username, password=password, database=database)
        connection.close()
        return ""
    except pymysql.MySQLError:
        root_password = simpledialog.askstring("MariaDB setup", "Enter the MariaDB root password:", show="*")
        if root_password is None:
            return "MariaDB setup was cancelled."
        try:
            connection = pymysql.connect(host="127.0.0.1", port=DATABASE_PORT, user="root", password=root_password)
            with connection.cursor() as cursor:
                cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{database}`")
                cursor.execute("CREATE USER IF NOT EXISTS %s@'localhost' IDENTIFIED BY %s", (username, password))
                cursor.execute(f"GRANT ALL PRIVILEGES ON `{database}`.* TO %s@'localhost'", (username,))
                cursor.execute("FLUSH PRIVILEGES")
            connection.commit()
            connection.close()
            return ""
        except pymysql.MySQLError as error:
            return f"MariaDB credentials or permissions were rejected: {error}"


def prepare_database() -> tuple[bool, str]:
    if not _port_open():
        started = False
        start_error = ""
        compose = shutil.which("docker")
        if compose:
            result = _run(["docker", "compose", "up", "-d", "mariadb"])
            if result.returncode != 0:
                return False, result.stderr.strip() or "Docker could not start MariaDB."
            started = True
        else:
            started, start_error = _start_local_service()
        if not _port_open() and not started:
            if start_error and "No MariaDB/MySQL Windows service was found" not in start_error:
                return False, f"{start_error} Run this control app as Administrator if Windows denied service control."
            if not messagebox.askyesno("MariaDB setup", "MariaDB is not running. Install or repair it automatically using this computer's package manager?"):
                return False, "MariaDB installation was cancelled."
            error = _install_database()
            if error:
                return False, error
            started, start_error = _start_local_service()
            if not started:
                return False, start_error or "MariaDB was installed, but its service could not be started. Run this control app as Administrator."
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and not _port_open():
            time.sleep(1)
    if not _port_open():
        return False, "MariaDB is not listening on port 3306."
    error = _configure_database()
    if error:
        return False, error
    virtual_python = PROJECT_ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    python_executable = str(virtual_python) if virtual_python.exists() else sys.executable
    seed = _run([python_executable, "-m", "backend.seed"])
    if seed.returncode != 0:
        return False, seed.stderr.strip() or "Database initialization failed."
    return True, "MariaDB is ready."
