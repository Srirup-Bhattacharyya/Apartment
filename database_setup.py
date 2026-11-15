import os
import platform
import re
import shutil
import socket
import subprocess
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


def _start_local_service() -> bool:
    system = platform.system()
    if system == "Windows":
        for service in ("MariaDB", "MySQL", "MySQL80"):
            result = _run(["sc.exe", "start", service])
            if result.returncode == 0 or "already been started" in result.stdout.lower():
                return True
        return False
    if system == "Darwin":
        result = _run(["brew", "services", "start", "mariadb"])
        return result.returncode == 0
    result = _run(["sudo", "systemctl", "start", "mariadb"])
    return result.returncode == 0


def _install_database() -> str:
    system = platform.system()
    if system == "Windows" and shutil.which("winget"):
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
        compose = shutil.which("docker")
        if compose:
            result = _run(["docker", "compose", "up", "-d", "mariadb"])
            if result.returncode != 0:
                return False, result.stderr.strip() or "Docker could not start MariaDB."
        elif not _start_local_service():
            if not messagebox.askyesno("MariaDB is not installed", "MariaDB was not found. Install it automatically using this computer's package manager?"):
                return False, "MariaDB installation was cancelled."
            error = _install_database()
            if error:
                return False, error
            if not _start_local_service():
                return False, "MariaDB was installed, but its service could not be started."
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and not _port_open():
            time.sleep(1)
    if not _port_open():
        return False, "MariaDB is not listening on port 3306."
    error = _configure_database()
    if error:
        return False, error
    seed = _run([str(PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"), "-m", "backend.seed"] if os.name == "nt" else ["python3", "-m", "backend.seed"])
    if seed.returncode != 0:
        return False, seed.stderr.strip() or "Database initialization failed."
    return True, "MariaDB is ready."
