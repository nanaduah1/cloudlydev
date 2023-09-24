import time
from typing import Any, Callable, Iterable


def parse_interval(interval: str) -> int:
    if interval.endswith("ms"):
        return int(interval[:-2])
    elif interval.endswith("s"):
        return int(interval[:-1]) * 1000
    elif interval.endswith("m"):
        return int(interval[:-1]) * 1000 * 60
    elif interval.endswith("h"):
        return int(interval[:-1]) * 1000 * 60 * 60
    elif interval.isdigit():
        return int(interval)

    raise ValueError("Invalid interval format")


class LambdaCronRunner:
    def __init__(self, handlers: Iterable[Callable[[dict, Any], Any]], interval="1m"):
        self._handlers = handlers
        self._interval = parse_interval(interval)
        self._exit = False

    def start(self):
        while self._exit is False:
            for handler in self._handlers:
                handler({}, None)
            time.sleep(self._interval)
