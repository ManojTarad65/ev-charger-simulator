from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional, Set

from fastapi import WebSocket

from .charger import Charger
from .models import CreateChargerRequest


class ChargerManager:
    def __init__(self) -> None:
        self.chargers: Dict[str, Charger] = {}
        self.ui_clients: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def broadcast(self, event: str, data: Dict[str, Any]) -> None:
        if not self.ui_clients:
            return
        message = json.dumps({"event": event, "data": data})
        dead: List[WebSocket] = []
        for ws in list(self.ui_clients):
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.ui_clients.discard(ws)

    async def register_ui_client(self, ws: WebSocket) -> None:
        self.ui_clients.add(ws)

    def unregister_ui_client(self, ws: WebSocket) -> None:
        self.ui_clients.discard(ws)

    async def create_charger(self, req: CreateChargerRequest) -> Charger:
        async with self._lock:
            if req.charger_id in self.chargers:
                raise ValueError(f"Charger {req.charger_id} already exists")
            charger = Charger(
                charger_id=req.charger_id,
                vendor=req.vendor,
                model=req.model,
                serial_number=req.serial_number,
                firmware_version=req.firmware_version,
                iccid=req.iccid,
                imsi=req.imsi,
                meter_type=req.meter_type,
                meter_serial_number=req.meter_serial_number,
                number_of_connectors=req.number_of_connectors,
                broadcaster=self.broadcast,
            )
            self.chargers[req.charger_id] = charger
            await self.broadcast("charger_created", {"charger_id": req.charger_id, "state": charger.snapshot()})
            return charger

    async def delete_charger(self, charger_id: str) -> None:
        async with self._lock:
            charger = self.chargers.pop(charger_id, None)
            if charger is not None:
                try:
                    await charger.disconnect()
                except Exception:
                    pass
                await self.broadcast("charger_deleted", {"charger_id": charger_id})

    def get(self, charger_id: str) -> Optional[Charger]:
        return self.chargers.get(charger_id)

    def require(self, charger_id: str) -> Charger:
        c = self.get(charger_id)
        if c is None:
            raise KeyError(charger_id)
        return c

    def list_snapshots(self) -> List[Dict[str, Any]]:
        return [c.snapshot() for c in self.chargers.values()]


manager = ChargerManager()
