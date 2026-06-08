"""OCPP 1.6J Charge Point simulator.

Implements the OCPP-J wire protocol directly (CALL=2, CALLRESULT=3, CALLERROR=4)
so every message is fully observable in the live log. Conforms to the OCPP 1.6
specification and interoperates with SteVe, commercial CSMS platforms, etc.
"""
from __future__ import annotations

import asyncio
import base64
import json
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Deque, Dict, List, Optional, Tuple

import websockets
from websockets.client import WebSocketClientProtocol

from .models import LogEntry

OCPP_SUBPROTOCOL = "ocpp1.6"

CALL = 2
CALLRESULT = 3
CALLERROR = 4

LOG_MAX = 1000


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class Charger:
    def __init__(
        self,
        charger_id: str,
        vendor: str = "Trodec",
        model: str = "AC_7KW",
        serial_number: str = "SIM000000",
        firmware_version: str = "1.0.0",
        iccid: str = "",
        imsi: str = "",
        meter_type: str = "AC",
        meter_serial_number: str = "MET000000",
        number_of_connectors: int = 1,
        broadcaster: Optional[Callable[[str, Dict[str, Any]], Awaitable[None]]] = None,
    ) -> None:
        self.charger_id = charger_id
        self.vendor = vendor
        self.model = model
        self.serial_number = serial_number
        self.firmware_version = firmware_version
        self.iccid = iccid
        self.imsi = imsi
        self.meter_type = meter_type
        self.meter_serial_number = meter_serial_number
        self.number_of_connectors = max(1, number_of_connectors)

        self.ws: Optional[WebSocketClientProtocol] = None
        self.csms_url: Optional[str] = None
        self.basic_auth: Optional[Tuple[str, str]] = None
        self.connected: bool = False

        self.status: str = "Available"
        self.last_status_per_connector: Dict[int, str] = {
            i: "Available" for i in range(0, self.number_of_connectors + 1)
        }
        self.transaction_id: Optional[int] = None
        self.id_tag_in_transaction: Optional[str] = None
        self.energy_wh: float = 0.0
        self.meter_start_wh: float = 0.0
        self.boot_accepted: bool = False
        self.last_heartbeat: Optional[str] = None

        self.heartbeat_interval: int = 30
        self.meter_interval: int = 10
        self.meter_enabled: bool = True
        self.meter_voltage: float = 230.0
        self.meter_current: float = 16.0
        self.meter_power_kw: float = 7.0

        self.pending: Dict[str, asyncio.Future] = {}
        self.logs: Deque[LogEntry] = deque(maxlen=LOG_MAX)
        self._listener_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._meter_task: Optional[asyncio.Task] = None
        self._reconnect_task: Optional[asyncio.Task] = None

        self._broadcaster = broadcaster
        self._stop_flag = False

    # ------------------------------------------------------------------ utils
    async def _broadcast(self, event: str, data: Dict[str, Any]) -> None:
        if self._broadcaster:
            try:
                await self._broadcaster(event, data)
            except Exception:  # broadcast failures must not crash the charger
                pass

    def _log(
        self,
        direction: str,
        message_type: str,
        action: Optional[str],
        message_id: Optional[str],
        payload: Any,
        raw: Optional[str] = None,
    ) -> LogEntry:
        entry = LogEntry(
            timestamp=utcnow_iso(),
            direction=direction,
            message_type=message_type,
            action=action,
            message_id=message_id,
            payload=payload,
            raw=raw,
        )
        self.logs.append(entry)
        asyncio.create_task(
            self._broadcast(
                "log",
                {"charger_id": self.charger_id, "entry": entry.model_dump()},
            )
        )
        return entry

    def _emit_state(self) -> None:
        asyncio.create_task(
            self._broadcast(
                "state",
                {"charger_id": self.charger_id, "state": self.snapshot()},
            )
        )

    def snapshot(self) -> Dict[str, Any]:
        return {
            "charger_id": self.charger_id,
            "vendor": self.vendor,
            "model": self.model,
            "serial_number": self.serial_number,
            "firmware_version": self.firmware_version,
            "connected": self.connected,
            "csms_url": self.csms_url,
            "status": self.status,
            "transaction_id": self.transaction_id,
            "id_tag_in_transaction": self.id_tag_in_transaction,
            "energy_wh": round(self.energy_wh, 2),
            "heartbeat_interval": self.heartbeat_interval,
            "meter_interval": self.meter_interval,
            "last_heartbeat": self.last_heartbeat,
            "boot_accepted": self.boot_accepted,
            "last_status_per_connector": self.last_status_per_connector,
            "number_of_connectors": self.number_of_connectors,
        }

    # ------------------------------------------------------------------ connect
    async def connect(
        self,
        url: str,
        basic_auth_user: Optional[str] = None,
        basic_auth_password: Optional[str] = None,
    ) -> None:
        if self.connected:
            raise RuntimeError("Already connected")

        url = url.rstrip("/")
        if not url.endswith(self.charger_id):
            full_url = f"{url}/{self.charger_id}"
        else:
            full_url = url

        self.csms_url = full_url
        if basic_auth_user is not None:
            self.basic_auth = (basic_auth_user, basic_auth_password or "")

        headers: List[Tuple[str, str]] = []
        if self.basic_auth:
            user, password = self.basic_auth
            token = base64.b64encode(f"{user}:{password}".encode()).decode()
            headers.append(("Authorization", f"Basic {token}"))

        self._log("SYS", "INFO", None, None, {"event": "connecting", "url": full_url})

        self.ws = await websockets.connect(
            full_url,
            subprotocols=[OCPP_SUBPROTOCOL],
            extra_headers=headers if headers else None,
            ping_interval=30,
            ping_timeout=20,
            max_size=2**22,
        )
        self.connected = True
        self._stop_flag = False
        self._log("SYS", "INFO", None, None, {"event": "connected"})
        self._emit_state()

        self._listener_task = asyncio.create_task(self._listen())
        # Boot then heartbeat
        try:
            await self.send_boot_notification()
        except Exception as exc:
            self._log("SYS", "INFO", None, None, {"event": "boot_failed", "error": str(exc)})

    async def disconnect(self) -> None:
        self._stop_flag = True
        self.connected = False
        for task in (self._heartbeat_task, self._meter_task, self._listener_task):
            if task and not task.done():
                task.cancel()
        if self.ws is not None:
            try:
                await self.ws.close()
            except Exception:
                pass
        self.ws = None
        self.boot_accepted = False
        self._log("SYS", "INFO", None, None, {"event": "disconnected"})
        self._emit_state()

    # ------------------------------------------------------------------ wire
    async def _listen(self) -> None:
        try:
            assert self.ws is not None
            async for raw in self.ws:
                try:
                    msg = json.loads(raw)
                except Exception:
                    self._log("IN", "INFO", None, None, {"error": "bad_json", "raw": raw})
                    continue
                await self._dispatch(msg, raw)
        except websockets.ConnectionClosed as exc:
            self._log("SYS", "INFO", None, None, {"event": "connection_closed", "code": exc.code, "reason": exc.reason})
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            self._log("SYS", "INFO", None, None, {"event": "listener_error", "error": str(exc)})
        finally:
            self.connected = False
            self.boot_accepted = False
            for task in (self._heartbeat_task, self._meter_task):
                if task and not task.done():
                    task.cancel()
            self._emit_state()

    async def _dispatch(self, msg: List[Any], raw: str) -> None:
        if not isinstance(msg, list) or len(msg) < 3:
            return
        kind = msg[0]
        message_id = msg[1]
        if kind == CALLRESULT:
            payload = msg[2] if len(msg) > 2 else {}
            self._log("IN", "CALLRESULT", None, message_id, payload, raw)
            fut = self.pending.pop(message_id, None)
            if fut and not fut.done():
                fut.set_result(payload)
        elif kind == CALLERROR:
            err_code = msg[2] if len(msg) > 2 else "GenericError"
            err_desc = msg[3] if len(msg) > 3 else ""
            err_details = msg[4] if len(msg) > 4 else {}
            self._log(
                "IN",
                "CALLERROR",
                None,
                message_id,
                {"errorCode": err_code, "errorDescription": err_desc, "errorDetails": err_details},
                raw,
            )
            fut = self.pending.pop(message_id, None)
            if fut and not fut.done():
                fut.set_exception(RuntimeError(f"{err_code}: {err_desc}"))
        elif kind == CALL:
            action = msg[2]
            payload = msg[3] if len(msg) > 3 else {}
            self._log("IN", "CALL", action, message_id, payload, raw)
            response = await self._handle_call(action, payload)
            out = [CALLRESULT, message_id, response]
            raw_out = json.dumps(out)
            try:
                await self.ws.send(raw_out)  # type: ignore[union-attr]
                self._log("OUT", "CALLRESULT", action, message_id, response, raw_out)
            except Exception as exc:
                self._log("SYS", "INFO", action, message_id, {"error": str(exc)})

    async def _send_call(self, action: str, payload: Dict[str, Any], timeout: float = 30.0) -> Dict[str, Any]:
        if not self.ws or not self.connected:
            raise RuntimeError("Not connected")
        message_id = str(uuid.uuid4())
        frame = [CALL, message_id, action, payload]
        raw = json.dumps(frame)
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self.pending[message_id] = fut
        await self.ws.send(raw)
        self._log("OUT", "CALL", action, message_id, payload, raw)
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            self.pending.pop(message_id, None)
            raise

    # ------------------------------------------------------------------ outgoing OCPP messages
    async def send_boot_notification(self) -> Dict[str, Any]:
        payload = {
            "chargePointVendor": self.vendor,
            "chargePointModel": self.model,
            "chargePointSerialNumber": self.serial_number,
            "firmwareVersion": self.firmware_version,
            "iccid": self.iccid,
            "imsi": self.imsi,
            "meterType": self.meter_type,
            "meterSerialNumber": self.meter_serial_number,
        }
        result = await self._send_call("BootNotification", payload)
        if result.get("status") == "Accepted":
            self.boot_accepted = True
            self.heartbeat_interval = int(result.get("interval", self.heartbeat_interval) or self.heartbeat_interval)
            self._start_heartbeat_loop()
            await self.send_status_notification(0, "Available")
            for i in range(1, self.number_of_connectors + 1):
                await self.send_status_notification(i, "Available")
        self._emit_state()
        return result

    async def send_heartbeat(self) -> Dict[str, Any]:
        result = await self._send_call("Heartbeat", {})
        self.last_heartbeat = result.get("currentTime", utcnow_iso())
        self._emit_state()
        return result

    async def send_status_notification(
        self,
        connector_id: int,
        status: str,
        error_code: str = "NoError",
        info: Optional[str] = None,
        vendor_id: Optional[str] = None,
        vendor_error_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "connectorId": connector_id,
            "errorCode": error_code,
            "status": status,
            "timestamp": utcnow_iso(),
        }
        if info:
            payload["info"] = info
        if vendor_id:
            payload["vendorId"] = vendor_id
        if vendor_error_code:
            payload["vendorErrorCode"] = vendor_error_code
        result = await self._send_call("StatusNotification", payload)
        self.last_status_per_connector[connector_id] = status
        if connector_id == 1 or self.number_of_connectors == 1:
            self.status = status
        self._emit_state()
        return result

    async def send_authorize(self, id_tag: str) -> Dict[str, Any]:
        return await self._send_call("Authorize", {"idTag": id_tag})

    async def send_start_transaction(
        self, connector_id: int, id_tag: str, meter_start: int = 0, reservation_id: Optional[int] = None
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "connectorId": connector_id,
            "idTag": id_tag,
            "meterStart": meter_start,
            "timestamp": utcnow_iso(),
        }
        if reservation_id is not None:
            payload["reservationId"] = reservation_id
        result = await self._send_call("StartTransaction", payload)
        info = result.get("idTagInfo", {}) if isinstance(result, dict) else {}
        if info.get("status") == "Accepted":
            self.transaction_id = int(result.get("transactionId", 0))
            self.id_tag_in_transaction = id_tag
            self.meter_start_wh = float(meter_start)
            self.energy_wh = float(meter_start)
            await self.send_status_notification(connector_id, "Preparing")
            await asyncio.sleep(0.5)
            await self.send_status_notification(connector_id, "Charging")
            self._start_meter_loop(connector_id)
        self._emit_state()
        return result

    async def send_stop_transaction(
        self,
        transaction_id: int,
        id_tag: Optional[str] = None,
        meter_stop: Optional[int] = None,
        reason: str = "Local",
    ) -> Dict[str, Any]:
        if meter_stop is None:
            meter_stop = int(self.energy_wh)
        payload: Dict[str, Any] = {
            "transactionId": transaction_id,
            "meterStop": meter_stop,
            "timestamp": utcnow_iso(),
            "reason": reason,
        }
        if id_tag:
            payload["idTag"] = id_tag
        result = await self._send_call("StopTransaction", payload)
        self._stop_meter_loop()
        connector_id = 1
        await self.send_status_notification(connector_id, "Finishing")
        await asyncio.sleep(0.5)
        await self.send_status_notification(connector_id, "Available")
        self.transaction_id = None
        self.id_tag_in_transaction = None
        self._emit_state()
        return result

    async def send_meter_values(self, connector_id: int = 1) -> Dict[str, Any]:
        if self.transaction_id is None:
            return {}
        sampled: List[Dict[str, Any]] = [
            {
                "value": f"{self.energy_wh:.2f}",
                "context": "Sample.Periodic",
                "format": "Raw",
                "measurand": "Energy.Active.Import.Register",
                "location": "Outlet",
                "unit": "Wh",
            },
            {
                "value": f"{self.meter_power_kw * 1000:.2f}",
                "context": "Sample.Periodic",
                "format": "Raw",
                "measurand": "Power.Active.Import",
                "location": "Outlet",
                "unit": "W",
            },
            {
                "value": f"{self.meter_voltage:.1f}",
                "context": "Sample.Periodic",
                "format": "Raw",
                "measurand": "Voltage",
                "location": "Outlet",
                "unit": "V",
            },
            {
                "value": f"{self.meter_current:.2f}",
                "context": "Sample.Periodic",
                "format": "Raw",
                "measurand": "Current.Import",
                "location": "Outlet",
                "unit": "A",
            },
        ]
        payload = {
            "connectorId": connector_id,
            "transactionId": self.transaction_id,
            "meterValue": [{"timestamp": utcnow_iso(), "sampledValue": sampled}],
        }
        result = await self._send_call("MeterValues", payload)
        return result

    async def send_data_transfer(self, vendor_id: str, message_id: Optional[str] = None, data: Optional[str] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"vendorId": vendor_id}
        if message_id:
            payload["messageId"] = message_id
        if data is not None:
            payload["data"] = data
        return await self._send_call("DataTransfer", payload)

    async def send_custom(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await self._send_call(action, payload)

    # ------------------------------------------------------------------ background loops
    def _start_heartbeat_loop(self) -> None:
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def _heartbeat_loop(self) -> None:
        try:
            while self.connected and not self._stop_flag:
                await asyncio.sleep(max(5, self.heartbeat_interval))
                if not self.connected:
                    break
                try:
                    await self.send_heartbeat()
                except Exception as exc:
                    self._log("SYS", "INFO", "Heartbeat", None, {"error": str(exc)})
                    break
        except asyncio.CancelledError:
            pass

    def _start_meter_loop(self, connector_id: int = 1) -> None:
        if self._meter_task and not self._meter_task.done():
            self._meter_task.cancel()
        self._meter_task = asyncio.create_task(self._meter_loop(connector_id))

    def _stop_meter_loop(self) -> None:
        if self._meter_task and not self._meter_task.done():
            self._meter_task.cancel()
        self._meter_task = None

    async def _meter_loop(self, connector_id: int) -> None:
        try:
            while self.connected and self.transaction_id is not None and not self._stop_flag:
                if self.meter_enabled:
                    interval = max(2, self.meter_interval)
                    increment_wh = (self.meter_power_kw * 1000.0) * (interval / 3600.0)
                    self.energy_wh += increment_wh
                    try:
                        await self.send_meter_values(connector_id)
                    except Exception as exc:
                        self._log("SYS", "INFO", "MeterValues", None, {"error": str(exc)})
                        break
                    self._emit_state()
                await asyncio.sleep(max(2, self.meter_interval))
        except asyncio.CancelledError:
            pass

    # ------------------------------------------------------------------ incoming CSMS commands
    async def _handle_call(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        handler = getattr(self, f"on_{action}", None)
        if handler is None:
            return {"status": "NotImplemented"}
        try:
            return await handler(payload)
        except Exception as exc:
            self._log("SYS", "INFO", action, None, {"error": str(exc)})
            return {"status": "Rejected"}

    async def on_RemoteStartTransaction(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        id_tag = payload.get("idTag", "REMOTE")
        connector_id = int(payload.get("connectorId", 1))
        asyncio.create_task(self._delayed_start(connector_id, id_tag))
        return {"status": "Accepted"}

    async def _delayed_start(self, connector_id: int, id_tag: str) -> None:
        await asyncio.sleep(0.5)
        try:
            await self.send_authorize(id_tag)
            await self.send_start_transaction(connector_id, id_tag, meter_start=int(self.energy_wh))
        except Exception as exc:
            self._log("SYS", "INFO", "RemoteStartTransaction", None, {"error": str(exc)})

    async def on_RemoteStopTransaction(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        tx = payload.get("transactionId")
        if tx is None or self.transaction_id != tx:
            return {"status": "Rejected"}
        asyncio.create_task(self._delayed_stop(int(tx)))
        return {"status": "Accepted"}

    async def _delayed_stop(self, transaction_id: int) -> None:
        await asyncio.sleep(0.5)
        try:
            await self.send_stop_transaction(transaction_id, id_tag=self.id_tag_in_transaction, reason="Remote")
        except Exception as exc:
            self._log("SYS", "INFO", "RemoteStopTransaction", None, {"error": str(exc)})

    async def on_Reset(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        reset_type = payload.get("type", "Soft")
        asyncio.create_task(self._reset_flow(reset_type))
        return {"status": "Accepted"}

    async def _reset_flow(self, reset_type: str) -> None:
        await asyncio.sleep(0.5)
        url = self.csms_url
        auth = self.basic_auth
        try:
            if self.transaction_id is not None:
                try:
                    await self.send_stop_transaction(self.transaction_id, reason="HardReset" if reset_type == "Hard" else "SoftReset")
                except Exception:
                    pass
            await self.disconnect()
        except Exception:
            pass
        await asyncio.sleep(1.5)
        if url:
            try:
                user, pwd = (auth or (None, None))
                await self.connect(url.rsplit("/", 1)[0], user, pwd)
            except Exception as exc:
                self._log("SYS", "INFO", "Reset", None, {"error": str(exc)})

    async def on_ChangeAvailability(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        connector_id = int(payload.get("connectorId", 0))
        availability = payload.get("type", "Operative")
        target_status = "Available" if availability == "Operative" else "Unavailable"
        asyncio.create_task(self._delayed_status_change(connector_id, target_status))
        return {"status": "Accepted"}

    async def _delayed_status_change(self, connector_id: int, target_status: str) -> None:
        await asyncio.sleep(0.3)
        try:
            if connector_id == 0:
                for i in range(0, self.number_of_connectors + 1):
                    await self.send_status_notification(i, target_status)
            else:
                await self.send_status_notification(connector_id, target_status)
        except Exception as exc:
            self._log("SYS", "INFO", "ChangeAvailability", None, {"error": str(exc)})

    async def on_TriggerMessage(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        requested = payload.get("requestedMessage")
        connector_id = int(payload.get("connectorId", 1))
        if requested not in {"BootNotification", "Heartbeat", "StatusNotification", "MeterValues", "DiagnosticsStatusNotification", "FirmwareStatusNotification"}:
            return {"status": "NotImplemented"}
        asyncio.create_task(self._trigger_message(requested, connector_id))
        return {"status": "Accepted"}

    async def _trigger_message(self, requested: str, connector_id: int) -> None:
        await asyncio.sleep(0.3)
        try:
            if requested == "BootNotification":
                await self.send_boot_notification()
            elif requested == "Heartbeat":
                await self.send_heartbeat()
            elif requested == "StatusNotification":
                await self.send_status_notification(connector_id, self.status)
            elif requested == "MeterValues":
                if self.transaction_id is not None:
                    await self.send_meter_values(connector_id)
            elif requested == "DiagnosticsStatusNotification":
                await self._send_call("DiagnosticsStatusNotification", {"status": "Idle"})
            elif requested == "FirmwareStatusNotification":
                await self._send_call("FirmwareStatusNotification", {"status": "Idle"})
        except Exception as exc:
            self._log("SYS", "INFO", requested, None, {"error": str(exc)})

    async def on_UnlockConnector(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "Unlocked"}

    async def on_ChangeConfiguration(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        key = payload.get("key", "")
        value = payload.get("value", "")
        if key == "HeartbeatInterval":
            try:
                self.heartbeat_interval = int(value)
                self._start_heartbeat_loop()
            except Exception:
                return {"status": "Rejected"}
        elif key == "MeterValueSampleInterval":
            try:
                self.meter_interval = int(value)
            except Exception:
                return {"status": "Rejected"}
        self._emit_state()
        return {"status": "Accepted"}

    async def on_GetConfiguration(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        keys: List[str] = payload.get("key", []) or []
        all_config = {
            "HeartbeatInterval": str(self.heartbeat_interval),
            "MeterValueSampleInterval": str(self.meter_interval),
            "NumberOfConnectors": str(self.number_of_connectors),
            "AuthorizeRemoteTxRequests": "true",
        }
        if not keys:
            items = [{"key": k, "readonly": False, "value": v} for k, v in all_config.items()]
            return {"configurationKey": items, "unknownKey": []}
        items = []
        unknown = []
        for k in keys:
            if k in all_config:
                items.append({"key": k, "readonly": False, "value": all_config[k]})
            else:
                unknown.append(k)
        return {"configurationKey": items, "unknownKey": unknown}

    async def on_DataTransfer(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "Accepted"}

    async def on_ClearCache(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "Accepted"}

    async def on_GetDiagnostics(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {"fileName": "diagnostics.log"}

    async def on_UpdateFirmware(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {}

    async def on_SendLocalList(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "Accepted"}

    async def on_GetLocalListVersion(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {"listVersion": 0}

    async def on_ReserveNow(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "Accepted"}

    async def on_CancelReservation(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "Accepted"}
