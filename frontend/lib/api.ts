export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
export const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000/ws/ui";

export type Charger = {
  charger_id: string;
  vendor: string;
  model: string;
  serial_number: string;
  firmware_version: string;
  connected: boolean;
  csms_url: string | null;
  status: string;
  transaction_id: number | null;
  id_tag_in_transaction: string | null;
  energy_wh: number;
  heartbeat_interval: number;
  meter_interval: number;
  last_heartbeat: string | null;
  boot_accepted: boolean;
  last_status_per_connector: Record<string, string>;
  number_of_connectors: number;
};

export type LogEntry = {
  timestamp: string;
  direction: "IN" | "OUT" | "SYS";
  message_type: "CALL" | "CALLRESULT" | "CALLERROR" | "INFO";
  action: string | null;
  message_id: string | null;
  payload: unknown;
  raw: string | null;
};

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return (await res.json()) as T;
  return (await res.text()) as unknown as T;
}

export const api = {
  listChargers: () => req<Charger[]>("/api/chargers"),
  createCharger: (body: Record<string, unknown>) =>
    req<Charger>("/api/chargers", { method: "POST", body: JSON.stringify(body) }),
  deleteCharger: (id: string) => req<{ deleted: string }>(`/api/chargers/${id}`, { method: "DELETE" }),
  connect: (id: string, body: { url: string; basic_auth_user?: string; basic_auth_password?: string }) =>
    req<Charger>(`/api/chargers/${id}/connect`, { method: "POST", body: JSON.stringify(body) }),
  disconnect: (id: string) => req<Charger>(`/api/chargers/${id}/disconnect`, { method: "POST" }),
  boot: (id: string) => req(`/api/chargers/${id}/boot`, { method: "POST" }),
  heartbeat: (id: string) => req(`/api/chargers/${id}/heartbeat`, { method: "POST" }),
  setHeartbeatInterval: (id: string, interval: number) =>
    req<Charger>(`/api/chargers/${id}/heartbeat-interval`, {
      method: "POST",
      body: JSON.stringify({ interval_seconds: interval }),
    }),
  status: (id: string, body: Record<string, unknown>) =>
    req(`/api/chargers/${id}/status`, { method: "POST", body: JSON.stringify(body) }),
  authorize: (id: string, idTag: string) =>
    req(`/api/chargers/${id}/authorize`, { method: "POST", body: JSON.stringify({ id_tag: idTag }) }),
  startTransaction: (id: string, body: { connector_id: number; id_tag: string; meter_start?: number }) =>
    req(`/api/chargers/${id}/start-transaction`, { method: "POST", body: JSON.stringify(body) }),
  stopTransaction: (id: string, body: { transaction_id: number; id_tag?: string; reason?: string }) =>
    req(`/api/chargers/${id}/stop-transaction`, { method: "POST", body: JSON.stringify(body) }),
  meterValues: (id: string, connectorId = 1) =>
    req(`/api/chargers/${id}/meter-values?connector_id=${connectorId}`, { method: "POST" }),
  meterConfig: (id: string, body: Record<string, unknown>) =>
    req<Charger>(`/api/chargers/${id}/meter-config`, { method: "POST", body: JSON.stringify(body) }),
  custom: (id: string, action: string, payload: unknown) =>
    req(`/api/chargers/${id}/custom`, { method: "POST", body: JSON.stringify({ action, payload }) }),
  getLogs: (id: string) => req<LogEntry[]>(`/api/chargers/${id}/logs`),
  clearLogs: (id: string) => req(`/api/chargers/${id}/logs`, { method: "DELETE" }),
  exportLogsUrl: (id: string, fmt: "json" | "csv" | "txt") => `${API_URL}/api/chargers/${id}/logs/export?format=${fmt}`,
};
