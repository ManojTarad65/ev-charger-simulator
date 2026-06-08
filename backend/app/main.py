from __future__ import annotations

import asyncio
import csv
import io
import json
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, Response

from .manager import manager
from .models import (
    AuthorizeRequest,
    ConnectRequest,
    CreateChargerRequest,
    CustomMessageRequest,
    HeartbeatConfig,
    MeterValuesConfig,
    StartTransactionRequest,
    StatusRequest,
    StopTransactionRequest,
)

app = FastAPI(title="EV Charger Simulator", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> Dict[str, Any]:
    return {"status": "ok", "chargers": len(manager.chargers)}


# ---------------------------------------------------------------- chargers CRUD
@app.get("/api/chargers")
async def list_chargers() -> List[Dict[str, Any]]:
    return manager.list_snapshots()


@app.post("/api/chargers", status_code=201)
async def create_charger(req: CreateChargerRequest) -> Dict[str, Any]:
    try:
        charger = await manager.create_charger(req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return charger.snapshot()


@app.delete("/api/chargers/{charger_id}")
async def delete_charger(charger_id: str) -> Dict[str, Any]:
    await manager.delete_charger(charger_id)
    return {"deleted": charger_id}


@app.get("/api/chargers/{charger_id}")
async def get_charger(charger_id: str) -> Dict[str, Any]:
    try:
        return manager.require(charger_id).snapshot()
    except KeyError:
        raise HTTPException(status_code=404, detail="Not found")


# ---------------------------------------------------------------- connection
@app.post("/api/chargers/{charger_id}/connect")
async def connect_charger(charger_id: str, req: ConnectRequest) -> Dict[str, Any]:
    try:
        charger = manager.require(charger_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        await charger.connect(req.url, req.basic_auth_user, req.basic_auth_password)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Connect failed: {exc}")
    return charger.snapshot()


@app.post("/api/chargers/{charger_id}/disconnect")
async def disconnect_charger(charger_id: str) -> Dict[str, Any]:
    try:
        charger = manager.require(charger_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Not found")
    await charger.disconnect()
    return charger.snapshot()


# ---------------------------------------------------------------- OCPP actions
@app.post("/api/chargers/{charger_id}/boot")
async def boot(charger_id: str) -> Dict[str, Any]:
    charger = _require_connected(charger_id)
    return await charger.send_boot_notification()


@app.post("/api/chargers/{charger_id}/heartbeat")
async def heartbeat(charger_id: str) -> Dict[str, Any]:
    charger = _require_connected(charger_id)
    return await charger.send_heartbeat()


@app.post("/api/chargers/{charger_id}/heartbeat-interval")
async def set_heartbeat_interval(charger_id: str, cfg: HeartbeatConfig) -> Dict[str, Any]:
    charger = _require_charger(charger_id)
    charger.heartbeat_interval = max(5, int(cfg.interval_seconds))
    if charger.connected:
        charger._start_heartbeat_loop()
    charger._emit_state()
    return charger.snapshot()


@app.post("/api/chargers/{charger_id}/status")
async def status(charger_id: str, req: StatusRequest) -> Dict[str, Any]:
    charger = _require_connected(charger_id)
    return await charger.send_status_notification(
        req.connector_id,
        req.status,
        req.error_code,
        req.info,
        req.vendor_id,
        req.vendor_error_code,
    )


@app.post("/api/chargers/{charger_id}/authorize")
async def authorize(charger_id: str, req: AuthorizeRequest) -> Dict[str, Any]:
    charger = _require_connected(charger_id)
    return await charger.send_authorize(req.id_tag)


@app.post("/api/chargers/{charger_id}/start-transaction")
async def start_transaction(charger_id: str, req: StartTransactionRequest) -> Dict[str, Any]:
    charger = _require_connected(charger_id)
    try:
        await charger.send_authorize(req.id_tag)
    except Exception:
        pass
    return await charger.send_start_transaction(
        req.connector_id, req.id_tag, req.meter_start, req.reservation_id
    )


@app.post("/api/chargers/{charger_id}/stop-transaction")
async def stop_transaction(charger_id: str, req: StopTransactionRequest) -> Dict[str, Any]:
    charger = _require_connected(charger_id)
    tx = req.transaction_id or charger.transaction_id
    if tx is None:
        raise HTTPException(status_code=400, detail="No active transaction")
    return await charger.send_stop_transaction(
        transaction_id=tx,
        id_tag=req.id_tag or charger.id_tag_in_transaction,
        meter_stop=req.meter_stop,
        reason=req.reason,
    )


@app.post("/api/chargers/{charger_id}/meter-values")
async def meter_values(charger_id: str, connector_id: int = 1) -> Dict[str, Any]:
    charger = _require_connected(charger_id)
    return await charger.send_meter_values(connector_id)


@app.post("/api/chargers/{charger_id}/meter-config")
async def meter_config(charger_id: str, cfg: MeterValuesConfig) -> Dict[str, Any]:
    charger = _require_charger(charger_id)
    charger.meter_interval = max(2, cfg.interval_seconds)
    charger.meter_enabled = cfg.enabled
    charger.meter_voltage = cfg.voltage
    charger.meter_current = cfg.current
    charger.meter_power_kw = cfg.power_kw
    charger._emit_state()
    return charger.snapshot()


@app.post("/api/chargers/{charger_id}/custom")
async def send_custom(charger_id: str, req: CustomMessageRequest) -> Dict[str, Any]:
    charger = _require_connected(charger_id)
    return await charger.send_custom(req.action, req.payload)


# ---------------------------------------------------------------- logs
@app.get("/api/chargers/{charger_id}/logs")
async def get_logs(charger_id: str) -> List[Dict[str, Any]]:
    charger = _require_charger(charger_id)
    return [entry.model_dump() for entry in list(charger.logs)]


@app.delete("/api/chargers/{charger_id}/logs")
async def clear_logs(charger_id: str) -> Dict[str, Any]:
    charger = _require_charger(charger_id)
    charger.logs.clear()
    return {"cleared": charger_id}


@app.get("/api/chargers/{charger_id}/logs/export")
async def export_logs(charger_id: str, format: str = "json") -> Response:
    charger = _require_charger(charger_id)
    entries = [entry.model_dump() for entry in list(charger.logs)]
    fmt = format.lower()
    if fmt == "json":
        return Response(content=json.dumps(entries, indent=2), media_type="application/json")
    if fmt == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["timestamp", "direction", "message_type", "action", "message_id", "payload"])
        for e in entries:
            writer.writerow([
                e.get("timestamp"),
                e.get("direction"),
                e.get("message_type"),
                e.get("action") or "",
                e.get("message_id") or "",
                json.dumps(e.get("payload")),
            ])
        return Response(content=buffer.getvalue(), media_type="text/csv")
    if fmt == "txt":
        lines = []
        for e in entries:
            arrow = "→" if e["direction"] == "OUT" else ("←" if e["direction"] == "IN" else "·")
            lines.append(
                f"[{e['timestamp']}] {arrow} {e['message_type']} {e.get('action') or ''} {json.dumps(e['payload'])}"
            )
        return PlainTextResponse("\n".join(lines))
    raise HTTPException(status_code=400, detail="format must be json|csv|txt")


# ---------------------------------------------------------------- websocket UI
@app.websocket("/ws/ui")
async def ws_ui(websocket: WebSocket) -> None:
    await websocket.accept()
    await manager.register_ui_client(websocket)
    try:
        # Send initial snapshot
        await websocket.send_text(json.dumps({"event": "snapshot", "data": {"chargers": manager.list_snapshots()}}))
        while True:
            # Keep connection open; we only push, but accept pings/text from client
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=60)
            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({"event": "ping", "data": {}}))
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        manager.unregister_ui_client(websocket)


# ---------------------------------------------------------------- helpers
def _require_charger(charger_id: str):
    try:
        return manager.require(charger_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Charger not found")


def _require_connected(charger_id: str):
    charger = _require_charger(charger_id)
    if not charger.connected:
        raise HTTPException(status_code=400, detail="Charger not connected")
    return charger
