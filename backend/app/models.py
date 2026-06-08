from __future__ import annotations

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class CreateChargerRequest(BaseModel):
    charger_id: str = Field(..., description="Unique charge point identity")
    vendor: str = "Trodec"
    model: str = "AC_7KW"
    serial_number: str = "SIM000000"
    firmware_version: str = "1.0.0"
    iccid: str = ""
    imsi: str = ""
    meter_type: str = "AC"
    meter_serial_number: str = "MET000000"
    number_of_connectors: int = 1


class ConnectRequest(BaseModel):
    url: str = Field(..., description="ws:// or wss:// CSMS URL (without charger id)")
    basic_auth_user: Optional[str] = None
    basic_auth_password: Optional[str] = None


class HeartbeatConfig(BaseModel):
    interval_seconds: int = 30


class StatusRequest(BaseModel):
    connector_id: int = 1
    status: str = "Available"
    error_code: str = "NoError"
    info: Optional[str] = None
    vendor_id: Optional[str] = None
    vendor_error_code: Optional[str] = None


class AuthorizeRequest(BaseModel):
    id_tag: str


class StartTransactionRequest(BaseModel):
    connector_id: int = 1
    id_tag: str
    meter_start: int = 0
    reservation_id: Optional[int] = None


class StopTransactionRequest(BaseModel):
    transaction_id: int
    id_tag: Optional[str] = None
    meter_stop: Optional[int] = None
    reason: str = "Local"


class MeterValuesConfig(BaseModel):
    interval_seconds: int = 10
    connector_id: int = 1
    enabled: bool = True
    voltage: float = 230.0
    current: float = 16.0
    power_kw: float = 7.0


class CustomMessageRequest(BaseModel):
    action: str
    payload: Dict[str, Any] = Field(default_factory=dict)


class ChargerSnapshot(BaseModel):
    charger_id: str
    vendor: str
    model: str
    serial_number: str
    firmware_version: str
    connected: bool
    csms_url: Optional[str]
    status: str
    transaction_id: Optional[int]
    id_tag_in_transaction: Optional[str]
    energy_wh: float
    heartbeat_interval: int
    meter_interval: int
    last_heartbeat: Optional[str]
    boot_accepted: bool
    last_status_per_connector: Dict[int, str]
    number_of_connectors: int


class LogEntry(BaseModel):
    timestamp: str
    direction: str  # IN / OUT / SYS
    message_type: str  # CALL / CALLRESULT / CALLERROR / INFO
    action: Optional[str] = None
    message_id: Optional[str] = None
    payload: Any = None
    raw: Optional[str] = None
