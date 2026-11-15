import os
import subprocess
import sys
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox

from database_setup import prepare_database

PROJECT_ROOT = Path(__file__).resolve().parent
OFFLINE_PAGE = PROJECT_ROOT / "offline.html"
HOST = "127.0.0.1"
PORT = 8000


class ServerControl:
    def __init__(self, window: tk.Tk) -> None:
        self.window = window
        self.process: subprocess.Popen[str] | None = None
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
        self.set_offline_state()
        self.setup_button.configure(state=tk.NORMAL)
        webbrowser.open(OFFLINE_PAGE.as_uri())

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
