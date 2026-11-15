import os
import re
import subprocess
import sys
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox

from database_setup import prepare_database

PROJECT_ROOT = Path(__file__).resolve().parent
TUNNEL_LOG = PROJECT_ROOT / "cloudflared.log"
HOST = "127.0.0.1"
PORT = 8000


class ServerControl:
    def __init__(self, window: tk.Tk) -> None:
        self.window = window
        self.process: subprocess.Popen[str] | None = None
        self.tunnel_process: subprocess.Popen[str] | None = None
        self.button = tk.Button(
            window,
            command=self.toggle_server,
            font=("Segoe UI", 16, "bold"),
            height=3,
            width=22,
            relief=tk.FLAT,
        )
        self.button.pack(padx=34, pady=(20, 12))
        self.status = tk.Label(window, font=("Segoe UI", 11))
        self.status.pack(pady=(0, 20))
        self.public_url = tk.Label(window, text="Cloudflare tunnel: not running", font=("Segoe UI", 9), fg="#75807b", wraplength=300)
        self.public_url.pack(pady=(0, 12))
        self.setup_button = tk.Button(window, text="SET UP DATABASE", command=self.setup_database, font=("Segoe UI", 10), relief=tk.FLAT)
        self.setup_button.pack(pady=(0, 20))
        self.set_offline_state()
        window.protocol("WM_DELETE_WINDOW", self.close)

    def set_offline_state(self) -> None:
        self.button.configure(text="START SERVER", bg="#b83f49", fg="white")
        self.status.configure(text="Server is OFF", fg="#b83f49")

    def set_online_state(self) -> None:
        self.button.configure(text="STOP SERVER", bg="#1c8b5a", fg="white")
        self.status.configure(text="Server is ON", fg="#1c8b5a")

    def find_cloudflared(self) -> str | None:
        command = subprocess.run(["where.exe", "cloudflared"], capture_output=True, text=True, check=False)
        return command.stdout.splitlines()[0].strip() if command.returncode == 0 and command.stdout.strip() else None

    def install_cloudflared(self) -> str | None:
        if not messagebox.askyesno("Cloudflare Tunnel", "cloudflared is not installed. Install the free Cloudflare tunnel tool with winget?"):
            return None
        result = subprocess.run(
            ["winget", "install", "--id", "Cloudflare.cloudflared", "--exact", "--accept-source-agreements", "--accept-package-agreements"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            messagebox.showerror("Cloudflare setup failed", result.stderr.strip() or result.stdout.strip())
            return None
        return self.find_cloudflared()

    def start_tunnel(self) -> None:
        cloudflared = self.find_cloudflared() or self.install_cloudflared()
        if not cloudflared:
            self.public_url.configure(text="Cloudflare tunnel: not installed", fg="#b83f49")
            return
        log_file = TUNNEL_LOG.open("w", encoding="utf-8")
        self.tunnel_process = subprocess.Popen(
            [cloudflared, "tunnel", "--url", f"http://127.0.0.1:{PORT}"],
            cwd=PROJECT_ROOT,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
        log_file.close()
        self.public_url.configure(text="Cloudflare tunnel: starting...", fg="#75807b")
        self.window.after(1500, self.read_tunnel_url)

    def read_tunnel_url(self) -> None:
        if self.tunnel_process is None:
            return
        text = TUNNEL_LOG.read_text(encoding="utf-8", errors="replace") if TUNNEL_LOG.exists() else ""
        match = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", text)
        if match:
            url = match.group(0)
            self.public_url.configure(text=url, fg="#177b59", cursor="hand2")
            self.public_url.bind("<Button-1>", lambda _event: webbrowser.open(url))
            return
        if self.tunnel_process.poll() is None:
            self.window.after(1000, self.read_tunnel_url)
        else:
            self.public_url.configure(text="Cloudflare tunnel failed; see cloudflared.log", fg="#b83f49")

    def toggle_server(self) -> None:
        if self.process is None or self.process.poll() is not None:
            self.start_server()
        else:
            self.stop_server()

    def setup_database(self) -> None:
        ready, message = prepare_database()
        if ready:
            self.status.configure(text=message, fg="#1c8b5a")
            messagebox.showinfo("Database ready", message)
        else:
            self.status.configure(text="Database setup failed", fg="#b83f49")
            messagebox.showerror("Database setup failed", message)

    def start_server(self) -> None:
        ready, message = prepare_database()
        if not ready:
            messagebox.showerror("Database setup failed", message)
            self.set_offline_state()
            return
        python = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
        executable = str(python if python.exists() else sys.executable)
        try:
            self.process = subprocess.Popen(
                [
                    executable,
                    "-m",
                    "uvicorn",
                    "backend.main:app",
                    "--host",
                    "0.0.0.0",
                    "--port",
                    str(PORT),
                ],
                cwd=PROJECT_ROOT,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
            )
        except OSError as error:
            messagebox.showerror("Could not start server", str(error))
            self.set_offline_state()
            return
        self.set_online_state()
        self.setup_button.configure(state=tk.DISABLED)
        self.start_tunnel()
        self.window.after(1200, lambda: webbrowser.open(f"http://{HOST}:{PORT}"))

    def stop_server(self) -> None:
        if self.process is None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
        self.process = None
        if self.tunnel_process is not None and self.tunnel_process.poll() is None:
            self.tunnel_process.terminate()
            try:
                self.tunnel_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.tunnel_process.kill()
        self.tunnel_process = None
        self.set_offline_state()
        self.setup_button.configure(state=tk.NORMAL)
        self.public_url.configure(text="Cloudflare tunnel: not running", fg="#75807b")

    def close(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.stop_server()
        self.window.destroy()


window = tk.Tk()
window.title("Shraddhanjalli Apartment Server")
window.configure(bg="#f7f9f7")
window.resizable(False, False)
tk.Label(window, text="SA", bg="#d9f0e5", fg="#177b59", font=("Segoe UI", 24, "bold"), width=4, height=2).pack(pady=(24, 8))
tk.Label(window, text="Shraddhanjalli Apartment", bg="#f7f9f7", fg="#17231f", font=("Segoe UI", 15, "bold")).pack()
tk.Label(window, text="Server control", bg="#f7f9f7", fg="#75807b", font=("Segoe UI", 10)).pack()
ServerControl(window)
window.mainloop()
