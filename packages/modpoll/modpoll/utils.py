import threading
import datetime
from datetime import timezone

_thread_event = threading.Event()


def set_threading_event():
    _thread_event.set()


def on_threading_event() -> bool:
    return _thread_event.is_set()


def delay_thread(timeout: int):
    _thread_event.wait(timeout=timeout)


def get_utc_time():
    dt = datetime.datetime.now(timezone.utc)
    utc_time = dt.replace(tzinfo=timezone.utc)
    return utc_time.timestamp()
