"""Bound anonymous verification traffic without accounts or a persistent visitor identifier.

Limits are per API process, not a distributed quota. A multi-worker deployment needs a shared
edge limiter before increasing capacity. Image and text checks share the same budget.
"""

import threading
import time
from collections import OrderedDict, deque
from collections.abc import AsyncIterator

from fastapi import Request

from app.core.config import get_settings
from app.core.errors import ApiError


class PublicBudget:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        self.addresses: OrderedDict[str, deque[float]] = OrderedDict()
        self.day_started = time.monotonic()
        self.spent = 0
        self.active = 0

    def acquire(self, address: str) -> None:
        settings = get_settings()
        with self.lock:
            now = time.monotonic()
            if now - self.day_started >= 86_400:
                self.day_started, self.spent = now, 0
            if self.spent >= settings.public_checks_per_day:
                raise ApiError(429, "public_budget_exhausted", "Public checks are busy, try later")
            if self.active >= settings.public_checks_concurrency:
                raise ApiError(429, "public_checks_busy", "Public checks are busy, try later")
            queue = self.addresses.pop(address, deque())
            while queue and now - queue[0] >= 600:
                queue.popleft()
            if len(queue) >= settings.public_checks_per_window:
                self.addresses[address] = queue
                raise ApiError(429, "too_many_public_checks", "Too many checks, try later")
            queue.append(now)
            self.addresses[address] = queue
            while len(self.addresses) > 4096:
                self.addresses.popitem(last=False)
            self.spent += 1
            self.active += 1

    def release(self) -> None:
        with self.lock:
            self.active -= 1


budget = PublicBudget()


async def public_check_budget(request: Request) -> AsyncIterator[None]:
    budget.acquire(request.client.host if request.client else "unknown")
    try:
        yield
    finally:
        budget.release()
