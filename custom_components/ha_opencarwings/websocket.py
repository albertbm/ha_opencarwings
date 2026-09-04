"""Live updates from the server's `/ws/notif/` socket.

The server pushes each object as it writes it, so entities follow the car
instead of waiting for the next poll.
"""
from __future__ import annotations

import asyncio
import json
import logging

from .util import CarData

_LOGGER = logging.getLogger(__name__)

WS_PATH = "/ws/notif/"

# Backoff between reconnects, in seconds.
RETRY_DELAYS = (5, 10, 20, 40, 60)

EVENT_ALERT = "ha_opencarwings_alert"

DEFAULT_API_BASE_FALLBACK = "https://opencarwings.viaaq.eu"


def socket_url(base_url: str) -> str:
    """Turn the API base URL into the websocket URL."""
    base = (base_url or "").rstrip("/")
    if base.startswith("https://"):
        return f"wss://{base[len('https://'):]}{WS_PATH}"
    if base.startswith("http://"):
        return f"ws://{base[len('http://'):]}{WS_PATH}"
    return f"wss://{base}{WS_PATH}"


def apply_message(cars: list, message) -> list | None:
    """Merge one pushed object into the car list. None means nothing changed."""
    if not isinstance(message, dict):
        return None

    obj_type = message.get("type")
    data = message.get("data")
    if not isinstance(data, dict):
        return None

    if obj_type == "car":
        vin = data.get("vin")
        if not vin:
            return None
        for car in cars or []:
            if car.vin == vin:
                return list(cars) if car.apply_push("car", data) else None

        # A car added to the account arrives as a full object.
        added = CarData.from_push(vin, data)
        return [*(cars or []), added] if added else None

    # Nested objects arrive alone, carrying only their own id.
    if obj_type in ("ev_info", "location", "tcu_configuration"):
        for car in cars or []:
            nested = getattr(car.get_latest_car(), obj_type, None)
            if nested is not None and nested.id == data.get("id"):
                return list(cars) if car.apply_push(obj_type, data) else None

    return None


class CarWingsSocket:
    """Holds one websocket open and feeds the coordinator."""

    def __init__(self, hass, session, base_url: str, api_key: str, coordinator) -> None:
        self.hass = hass
        self._session = session
        self._url = socket_url(base_url)
        self._api_key = api_key
        self._coordinator = coordinator
        self._task: asyncio.Task | None = None
        self._closing = False

    def start(self) -> None:
        if self._task is not None:
            return
        # A plain task would hold up Home Assistant's startup.
        create = getattr(self.hass, "async_create_background_task", None) or self.hass.async_create_task
        self._task = create(self._run(), "ha_opencarwings websocket")

    async def stop(self) -> None:
        self._closing = True
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # pragma: no cover - shutdown
                pass
            self._task = None

    async def _run(self) -> None:
        attempt = 0
        while not self._closing:
            try:
                await self._listen()
                attempt = 0
            except asyncio.CancelledError:  # pragma: no cover - shutdown
                raise
            except Exception as err:
                _LOGGER.debug("OpenCARWINGS websocket dropped: %s", err)

            if self._closing:
                return
            delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
            attempt += 1
            await asyncio.sleep(delay)

    async def _listen(self) -> None:
        headers = {"Authorization": f"Token {self._api_key}"}
        async with self._session.ws_connect(self._url, headers=headers, heartbeat=30) as ws:
            _LOGGER.info("OpenCARWINGS live updates connected")
            async for msg in ws:
                data = getattr(msg, "data", None)
                if not isinstance(data, str):
                    continue
                try:
                    self._handle(json.loads(data))
                except Exception:  # pragma: no cover - malformed push
                    _LOGGER.debug("Ignoring unreadable websocket message")

    def _handle(self, message: dict) -> None:
        if message.get("type") == "alert":
            self._fire_alert(message.get("data"))
            return

        updated = apply_message(self._coordinator.data or [], message)
        if updated is not None:
            self._coordinator.async_set_updated_data(updated)

    def _fire_alert(self, alert) -> None:
        bus = getattr(self.hass, "bus", None)
        if not bus or not isinstance(alert, dict):
            return
        bus.async_fire(EVENT_ALERT, alert)
