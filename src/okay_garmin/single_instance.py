"""Single-instance guard and a quit channel for the updater.

v1 could be started any number of times, each copy grabbing the microphone.
The named event doubles as the signal the updater uses to ask a running
instance to exit -- far more reliable than v1's `tasklist | find "main.exe"`
polling, which also matched unrelated processes.
"""

import threading

import win32api
import win32event
import winerror

from .logging_setup import get_logger
from .version import APP_NAME

log = get_logger("single_instance")

MUTEX_NAME = f"Local\\{APP_NAME}-instance"
QUIT_EVENT_NAME = f"Local\\{APP_NAME}-quit"
SHOW_EVENT_NAME = f"Local\\{APP_NAME}-show"

_mutex = None


def acquire() -> bool:
    """Claim the single-instance mutex. False means another copy is running."""
    global _mutex
    _mutex = win32event.CreateMutex(None, False, MUTEX_NAME)
    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        log.info("Another instance is already running")
        return False
    return True


def signal_existing_instance(event_name: str) -> bool:
    """Pulse a named event in the already-running instance."""
    try:
        handle = win32event.OpenEvent(win32event.EVENT_MODIFY_STATE, False, event_name)
    except Exception:
        return False
    try:
        win32event.SetEvent(handle)
        return True
    finally:
        win32api.CloseHandle(handle)


def watch_event(event_name: str, callback, stop: threading.Event) -> threading.Thread:
    """Run `callback` whenever the named event is pulsed."""
    handle = win32event.CreateEvent(None, False, False, event_name)

    def loop() -> None:
        while not stop.is_set():
            result = win32event.WaitForSingleObject(handle, 500)
            if result == win32event.WAIT_OBJECT_0:
                try:
                    callback()
                except Exception:
                    log.exception("Event handler for %s failed", event_name)

    thread = threading.Thread(target=loop, name=f"watch:{event_name}", daemon=True)
    thread.start()
    return thread
