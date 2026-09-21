"""Garante uma única instância do MPP Sync no Windows."""

from __future__ import annotations

import os
import sys

MUTEX_NAME = "Global\\MPPSyncSingleton"
WINDOW_TITLE = "MPP Sync"

_mutex_handle = None


def acquire_single_instance() -> bool:
    """True se esta é a instância única; False se outra já está no ar.

    O handle do mutex precisa ficar vivo até o processo terminar.
    """
    if os.name != "nt":
        return True

    global _mutex_handle
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.argtypes = [
        wintypes.LPVOID,
        wintypes.BOOL,
        wintypes.LPCWSTR,
    ]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.GetLastError.restype = wintypes.DWORD

    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not handle:
        return True

    _mutex_handle = handle
    error_already_exists = 183
    return kernel32.GetLastError() != error_already_exists


def focus_existing_window() -> None:
    """Traz a janela da instância já aberta para frente, se existir."""
    if os.name != "nt":
        return

    import ctypes

    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, WINDOW_TITLE)
    if not hwnd:
        return

    sw_restore = 9
    user32.ShowWindow(hwnd, sw_restore)
    user32.SetForegroundWindow(hwnd)


def exit_if_already_running() -> None:
    """Encerra este processo se o MPP Sync já estiver aberto."""
    if acquire_single_instance():
        return
    focus_existing_window()
    sys.exit(0)
