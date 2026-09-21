"""Interface gráfica para controlar o watcher de arquivos .mpp."""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import messagebox, ttk

import pystray
from PIL import Image, ImageDraw

import autostart
from config import Settings, load_config_values, load_settings
from main import WatcherService
from updater import (
    APP_VERSION,
    ReleaseInfo,
    download_installer,
    fetch_latest_release,
    is_newer,
    launch_installer,
)

logger = logging.getLogger(__name__)

BG = "#faf8f4"
BORDER = "#d8d3ca"
TEXT = "#1f2430"
MUTED = "#6f7480"
GREEN = "#22c55e"
GRAY = "#6b7280"

MAX_FOLDER_DISPLAY_CHARS = 46


class App:
    """Janela principal e ícone de bandeja do watcher."""

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("MPP Sync")
        self.root.geometry("620x520")
        self.root.minsize(560, 470)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)

        self.service: WatcherService | None = None
        self.tray_icon: pystray.Icon | None = None
        self._is_quitting = False

        self.status_var = tk.StringVar(value="Desconectado")
        self.dsn_var = tk.StringVar(value=self._dsn_from_config())
        self.folder_var = tk.StringVar(value=self._folder_from_config())
        self.version_var = tk.StringVar(value=f"v{APP_VERSION}")
        self._update_in_progress = False

        self._configure_style()
        self._build_layout()
        self._ensure_autostart()
        self._refresh_status()
        self._start_tray_icon()

        self.root.after(300, self._auto_connect)

    def run(self) -> None:
        self.root.mainloop()

    def toggle_connection(self) -> None:
        if self.service is not None and self.service.is_running:
            self.disconnect()
        else:
            self.connect()

    def connect(self, *, silent: bool = False) -> None:
        if self.service is not None and self.service.is_running:
            return

        try:
            settings = load_settings()
            service = WatcherService(settings)
            service.start()
        except Exception as exc:
            if silent:
                logger.warning("Conexão automática falhou: %s", exc)
            else:
                messagebox.showerror("Falha ao conectar", str(exc), parent=self.root)
            return

        self.service = service
        self.dsn_var.set(self._dsn_from_settings(settings))
        self.folder_var.set(self._short_path(settings.local_mpp_dir))
        self._update_status()

    def disconnect(self) -> None:
        if self.service is None:
            self._update_status()
            return

        try:
            self.service.stop()
        except Exception as exc:
            messagebox.showerror("Falha ao desconectar", str(exc), parent=self.root)
        finally:
            self.service = None
            self._update_status()

    def hide_window(self) -> None:
        self.root.withdraw()

    def show_window(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def quit_app(self) -> None:
        self._is_quitting = True
        self.disconnect()
        if self.tray_icon is not None:
            self.tray_icon.stop()
        self.root.destroy()

    def check_for_updates(self) -> None:
        if self._update_in_progress:
            return
        self._update_in_progress = True
        self.update_button.state(["disabled"])
        threading.Thread(
            target=self._check_for_updates_worker,
            name="mpp-update",
            daemon=True,
        ).start()

    def _check_for_updates_worker(self) -> None:
        try:
            release = fetch_latest_release()
        except Exception as exc:
            self._call_on_ui(lambda: self._on_update_error(str(exc)))
            return

        if not is_newer(release.version):
            remote = release.version
            self._call_on_ui(
                lambda: self._on_update_finished(
                    f"Você já está na versão mais recente (v{APP_VERSION}).\n"
                    f"Release no GitHub: v{remote}."
                )
            )
            return

        self._call_on_ui(lambda: self._confirm_and_download_update(release))

    def _confirm_and_download_update(self, release: ReleaseInfo) -> None:
        confirmed = messagebox.askyesno(
            "Atualização disponível",
            f"Nova versão encontrada: v{release.version}\n"
            f"Versão instalada: v{APP_VERSION}\n\n"
            "Deseja baixar e instalar agora?\n"
            "Vai aparecer o UAC do Windows — aceite para continuar.\n"
            "O app fecha, instala e reabre uma única vez.",
            parent=self.root,
        )
        if not confirmed:
            self._on_update_finished()
            return

        self.update_button.configure(text="Baixando...")
        threading.Thread(
            target=self._download_and_install_worker,
            args=(release.download_url,),
            name="mpp-update-download",
            daemon=True,
        ).start()

    def _download_and_install_worker(self, download_url: str) -> None:
        try:
            installer_path = download_installer(download_url)
            log_path = launch_installer(installer_path)
        except Exception as exc:
            self._call_on_ui(lambda: self._on_update_error(str(exc)))
            return

        self._call_on_ui(lambda: self._on_update_launched(str(log_path)))

    def _on_update_launched(self, log_path: str) -> None:
        messagebox.showinfo(
            "Atualizando",
            "Aceite o UAC do Windows para instalar.\n\n"
            "O MPP Sync vai fechar, instalar a nova versão e reabrir uma vez.\n"
            "Se cancelar o UAC, o app continua aberto.\n\n"
            f"Se não reabrir, use o atalho do Menu Iniciar.\n"
            f"Log do update: {log_path}",
            parent=self.root,
        )
        # Não chama quit_app: se o UAC for cancelado, o app permanece.
        # Se aceitar, o .bat elevado mata este processo e reabre o exe novo.
        self._on_update_finished()

    def _on_update_error(self, message: str) -> None:
        messagebox.showerror("Falha na atualização", message, parent=self.root)
        self._on_update_finished()

    def _on_update_finished(self, info_message: str | None = None) -> None:
        self._update_in_progress = False
        self.update_button.state(["!disabled"])
        self.update_button.configure(text="Atualizar")
        if info_message:
            messagebox.showinfo("Atualização", info_message, parent=self.root)

    def _auto_connect(self) -> None:
        self.connect(silent=True)

    def _ensure_autostart(self) -> None:
        """Inicialização com o Windows é obrigatória; habilita em toda abertura."""
        if not autostart.is_supported():
            return
        try:
            autostart.enable()
        except Exception as exc:
            logger.warning("Não foi possível habilitar o autostart: %s", exc)

    def _build_layout(self) -> None:
        outer = tk.Frame(
            self.root,
            bg=BG,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        outer.pack(fill=tk.BOTH, expand=True, padx=36, pady=32)

        tk.Label(
            outer,
            text="MPP Sync",
            bg=BG,
            fg=TEXT,
            font=("Segoe UI", 22, "bold"),
        ).pack(pady=(28, 2))
        tk.Label(
            outer,
            text="Sincronize os arquivos .mpp com seu DSN",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 10),
        ).pack()
        tk.Label(
            outer,
            textvariable=self.version_var,
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 9),
        ).pack(pady=(4, 0))

        card = tk.Frame(
            outer,
            bg=BG,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        card.pack(fill=tk.X, padx=40, pady=(30, 0))

        status_row = tk.Frame(card, bg=BG)
        status_row.pack(pady=(24, 20))
        self.status_dot = tk.Canvas(
            status_row,
            width=14,
            height=14,
            bg=BG,
            highlightthickness=0,
        )
        self.status_dot.pack(side=tk.LEFT, padx=(0, 8), pady=2)
        self._draw_status_dot(False)
        tk.Label(
            status_row,
            textvariable=self.status_var,
            bg=BG,
            fg=TEXT,
            font=("Segoe UI", 13, "bold"),
        ).pack(side=tk.LEFT)

        info_row = tk.Frame(card, bg=BG)
        info_row.pack(fill=tk.X, padx=30, pady=(0, 28))
        info_row.columnconfigure(0, weight=1)
        info_row.columnconfigure(1, weight=1)

        dsn_col = tk.Frame(info_row, bg=BG)
        dsn_col.grid(row=0, column=0)
        tk.Label(
            dsn_col,
            text="DSN",
            bg=BG,
            fg=TEXT,
            font=("Segoe UI", 12, "bold"),
        ).pack()
        tk.Label(
            dsn_col,
            textvariable=self.dsn_var,
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 11),
        ).pack(pady=(2, 0))

        folder_col = tk.Frame(info_row, bg=BG)
        folder_col.grid(row=0, column=1)
        tk.Label(
            folder_col,
            text="Pasta monitorada",
            bg=BG,
            fg=TEXT,
            font=("Segoe UI", 12, "bold"),
        ).pack()
        tk.Label(
            folder_col,
            textvariable=self.folder_var,
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 10),
        ).pack(pady=(2, 0))

        self.toggle_button = ttk.Button(
            outer,
            text="Conectar",
            command=self.toggle_connection,
            style="Toggle.TButton",
        )
        self.toggle_button.pack(pady=(34, 12), ipadx=18)

        self.update_button = ttk.Button(
            outer,
            text="Atualizar",
            command=self.check_for_updates,
            style="Toggle.TButton",
        )
        self.update_button.pack(pady=(0, 24), ipadx=18)

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(
            "Toggle.TButton",
            background=BG,
            foreground=TEXT,
            bordercolor="#a8a29a",
            lightcolor=BG,
            darkcolor=BG,
            focusthickness=0,
            font=("Segoe UI", 10),
            padding=(20, 10),
        )
        style.map(
            "Toggle.TButton",
            background=[("active", "#efeae2"), ("disabled", BG)],
            foreground=[("disabled", MUTED)],
        )

    def _update_status(self) -> None:
        is_running = self.service is not None and self.service.is_running
        self.status_var.set("Conectado" if is_running else "Desconectado")
        self.toggle_button.configure(text="Desconectar" if is_running else "Conectar")
        self._draw_status_dot(is_running)

        if is_running and self.service is not None:
            self.dsn_var.set(self._dsn_from_settings(self.service.settings))
            self.folder_var.set(self._short_path(self.service.settings.local_mpp_dir))

    def _refresh_status(self) -> None:
        self._update_status()

        if not self._is_quitting:
            self.root.after(1000, self._refresh_status)

    def _start_tray_icon(self) -> None:
        self.tray_icon = pystray.Icon(
            "mpp-sync",
            self._create_tray_image(),
            "MPP Sync",
            menu=pystray.Menu(
                pystray.MenuItem("Mostrar", self._tray_show, default=True),
                pystray.MenuItem("Atualizar", self._tray_update),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Sair", self._tray_quit),
            ),
        )
        threading.Thread(target=self.tray_icon.run, name="mpp-tray", daemon=True).start()

    def _create_tray_image(self) -> Image.Image:
        image = Image.new("RGBA", (64, 64), (255, 255, 255, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((10, 8, 54, 56), radius=10, fill="#1f6feb")
        draw.rectangle((18, 20, 46, 26), fill="white")
        draw.rectangle((18, 32, 40, 38), fill="white")
        draw.rectangle((18, 44, 34, 50), fill="white")
        return image

    def _draw_status_dot(self, is_running: bool) -> None:
        self.status_dot.delete("all")
        color = GREEN if is_running else GRAY
        self.status_dot.create_oval(2, 2, 12, 12, fill=color, outline=color)

    def _dsn_from_config(self) -> str:
        values = load_config_values()
        dsn = values.get("ODBC_DSN", "").strip()
        if dsn:
            return dsn
        return self._extract_dsn(values.get("ODBC_CONNECT", "")) or "-"

    def _dsn_from_settings(self, settings: Settings) -> str:
        if settings.odbc_dsn:
            return settings.odbc_dsn
        if settings.odbc_connect:
            return self._extract_dsn(settings.odbc_connect) or "-"
        return "-"

    def _extract_dsn(self, odbc_connect: str) -> str | None:
        for part in odbc_connect.split(";"):
            key, separator, value = part.partition("=")
            if separator and key.strip().lower() == "dsn":
                return value.strip().strip('"') or None
        return None

    def _folder_from_config(self) -> str:
        raw = load_config_values().get("LOCAL_MPP_DIR", "").strip()
        if not raw:
            return "-"
        return self._short_path(Path(raw))

    def _short_path(self, path: Path) -> str:
        text = str(path)
        try:
            if path.is_relative_to(Path.home()):
                text = "~/" + str(path.relative_to(Path.home()))
        except OSError:
            pass
        if len(text) <= MAX_FOLDER_DISPLAY_CHARS:
            return text
        return f"…{text[-(MAX_FOLDER_DISPLAY_CHARS - 1):]}"

    def _call_on_ui(self, callback: Callable[[], None]) -> None:
        self.root.after(0, callback)

    def _tray_show(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        self._call_on_ui(self.show_window)

    def _tray_update(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        self._call_on_ui(self.check_for_updates)

    def _tray_quit(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        self._call_on_ui(self.quit_app)
