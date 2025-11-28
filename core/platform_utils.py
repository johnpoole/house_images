from __future__ import annotations

import os
import signal
import subprocess
import sys
from typing import Sequence


def get_background_python_executable() -> str:
    """Return the best Python interpreter for background processes on this OS."""
    if os.name == 'nt':
        pythonw = os.path.join(os.path.dirname(sys.executable), 'pythonw.exe')
        if os.path.exists(pythonw):
            return pythonw
    return sys.executable


def launch_detached_process(cmd: Sequence[str], cwd: str | None = None) -> subprocess.Popen:
    """Launch a background process, hiding windows on Windows and detaching on POSIX."""
    popen_kwargs: dict = {
        'cwd': cwd,
        'stdout': subprocess.DEVNULL,
        'stderr': subprocess.DEVNULL,
        'close_fds': True,
    }
    if os.name == 'nt':
        creationflags = (
            getattr(subprocess, 'DETACHED_PROCESS', 0)
            | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
            | getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        )
        popen_kwargs['creationflags'] = creationflags
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        popen_kwargs['startupinfo'] = startupinfo
    else:
        popen_kwargs['start_new_session'] = True
    return subprocess.Popen(cmd, **popen_kwargs)


def terminate_process(pid: int) -> bool:
    """Attempt to terminate a background process regardless of platform."""
    try:
        if os.name == 'nt':
            completed = subprocess.run(
                ['taskkill', '/PID', str(pid), '/T', '/F'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return completed.returncode == 0
        try:
            if hasattr(os, 'killpg'):
                os.killpg(pid, signal.SIGTERM)
            else:
                os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            return False
        except OSError:
            os.kill(pid, signal.SIGTERM)
        return True
    except (ProcessLookupError, PermissionError, OSError, subprocess.SubprocessError):
        return False
