"use client";
import { useState } from "react";
import { Play, Square, Heart, Wifi, WifiOff, Zap, Send, Trash2, RotateCcw } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Dialog } from "@/components/ui/dialog";
import { LogPanel } from "@/components/LogPanel";
import { api, Charger, LogEntry } from "@/lib/api";

const STATUS_OPTIONS = [
  "Available",
  "Preparing",
  "Charging",
  "SuspendedEV",
  "SuspendedEVSE",
  "Finishing",
  "Faulted",
  "Unavailable",
  "Reserved",
];

function statusVariant(s: string): "success" | "warning" | "destructive" | "info" | "secondary" {
  if (s === "Available") return "success";
  if (s === "Charging") return "info";
  if (s === "Faulted") return "destructive";
  if (s === "Unavailable") return "secondary";
  return "warning";
}

export function ChargerPanel({
  charger,
  logs,
  onRefresh,
  onDelete,
  onLogsCleared,
}: {
  charger: Charger;
  logs: LogEntry[];
  onRefresh: () => void;
  onDelete: () => void;
  onLogsCleared: () => void;
}) {
  const [url, setUrl] = useState("ws://localhost:9000");
  const [authUser, setAuthUser] = useState("");
  const [authPass, setAuthPass] = useState("");
  const [idTag, setIdTag] = useState("RFID-ABC123");
  const [connectorId, setConnectorId] = useState(1);
  const [hbInterval, setHbInterval] = useState(charger.heartbeat_interval);
  const [meterInterval, setMeterInterval] = useState(charger.meter_interval);
  const [meterPower, setMeterPower] = useState(7);
  const [customOpen, setCustomOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const run = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(label);
    setErr(null);
    try {
      await fn();
      onRefresh();
    } catch (e: any) {
      setErr(`${label}: ${e?.message || "Failed"}`);
    } finally {
      setBusy(null);
    }
  };

  return (
    <Card className="overflow-hidden">
      <CardHeader className="bg-muted/30">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div>
            <CardTitle className="text-base flex items-center gap-2">
              <Zap className="h-4 w-4 text-primary" />
              {charger.charger_id}
              <Badge variant={charger.connected ? "success" : "secondary"}>
                {charger.connected ? "CONNECTED" : "OFFLINE"}
              </Badge>
              <Badge variant={statusVariant(charger.status)}>{charger.status}</Badge>
              {charger.boot_accepted && <Badge variant="info">BOOT OK</Badge>}
            </CardTitle>
            <div className="text-xs text-muted-foreground mt-1">
              {charger.vendor} · {charger.model} · FW {charger.firmware_version} · {charger.number_of_connectors} connector(s)
            </div>
            {charger.csms_url && (
              <div className="text-xs text-muted-foreground mono mt-1">{charger.csms_url}</div>
            )}
          </div>
          <div className="flex flex-col items-end gap-1">
            <div className="text-xs text-muted-foreground">Energy</div>
            <div className="text-lg font-bold tabular-nums">{(charger.energy_wh / 1000).toFixed(3)} kWh</div>
            {charger.transaction_id !== null && (
              <Badge variant="info">TX #{charger.transaction_id}</Badge>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 p-0">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 p-4">
          {/* Connect */}
          <section className="space-y-2">
            <h3 className="text-sm font-semibold">CSMS Connection</h3>
            <div className="space-y-2">
              <div>
                <Label>WebSocket URL (without charger id)</Label>
                <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="ws://localhost:9000" />
                <div className="text-[10px] text-muted-foreground mt-1">
                  Final URL: {url.replace(/\/$/, "")}/{charger.charger_id}
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <Label>Basic Auth User (optional)</Label>
                  <Input value={authUser} onChange={(e) => setAuthUser(e.target.value)} />
                </div>
                <div>
                  <Label>Basic Auth Password (optional)</Label>
                  <Input type="password" value={authPass} onChange={(e) => setAuthPass(e.target.value)} />
                </div>
              </div>
              <div className="flex gap-2">
                {!charger.connected ? (
                  <Button
                    onClick={() =>
                      run("connect", () =>
                        api.connect(charger.charger_id, {
                          url,
                          basic_auth_user: authUser || undefined,
                          basic_auth_password: authPass || undefined,
                        })
                      )
                    }
                    disabled={busy === "connect"}
                  >
                    <Wifi className="h-4 w-4" /> Connect
                  </Button>
                ) : (
                  <Button variant="destructive" onClick={() => run("disconnect", () => api.disconnect(charger.charger_id))}>
                    <WifiOff className="h-4 w-4" /> Disconnect
                  </Button>
                )}
                <Button
                  variant="outline"
                  disabled={!charger.connected}
                  onClick={() => run("boot", () => api.boot(charger.charger_id))}
                >
                  Send BootNotification
                </Button>
              </div>
            </div>
          </section>

          {/* Heartbeat + Meter Config */}
          <section className="space-y-2">
            <h3 className="text-sm font-semibold">Intervals & Meter</h3>
            <div className="grid grid-cols-3 gap-2">
              <div>
                <Label>Heartbeat (s)</Label>
                <Input
                  type="number"
                  value={hbInterval}
                  onChange={(e) => setHbInterval(Number(e.target.value) || 30)}
                />
              </div>
              <div>
                <Label>Meter (s)</Label>
                <Input
                  type="number"
                  value={meterInterval}
                  onChange={(e) => setMeterInterval(Number(e.target.value) || 10)}
                />
              </div>
              <div>
                <Label>Power (kW)</Label>
                <Input
                  type="number"
                  step="0.1"
                  value={meterPower}
                  onChange={(e) => setMeterPower(Number(e.target.value) || 7)}
                />
              </div>
            </div>
            <div className="flex gap-2 flex-wrap">
              <Button
                size="sm"
                variant="outline"
                onClick={() =>
                  run("hb_interval", () => api.setHeartbeatInterval(charger.charger_id, hbInterval))
                }
              >
                Apply HB
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() =>
                  run("meter_cfg", () =>
                    api.meterConfig(charger.charger_id, {
                      interval_seconds: meterInterval,
                      power_kw: meterPower,
                      enabled: true,
                      voltage: 230,
                      current: meterPower * 1000 / 230,
                      connector_id: 1,
                    })
                  )
                }
              >
                Apply Meter
              </Button>
              <Button
                size="sm"
                disabled={!charger.connected}
                onClick={() => run("hb", () => api.heartbeat(charger.charger_id))}
              >
                <Heart className="h-3 w-3" /> Send Heartbeat
              </Button>
              <Button
                size="sm"
                disabled={!charger.connected || charger.transaction_id === null}
                onClick={() => run("mv", () => api.meterValues(charger.charger_id, 1))}
              >
                Send MeterValues
              </Button>
            </div>
          </section>

          {/* Status simulation */}
          <section className="space-y-2 lg:col-span-2">
            <h3 className="text-sm font-semibold">Status Simulation</h3>
            <div className="flex flex-wrap gap-1">
              {STATUS_OPTIONS.map((s) => (
                <Button
                  key={s}
                  size="sm"
                  variant={charger.status === s ? "default" : "outline"}
                  disabled={!charger.connected}
                  onClick={() =>
                    run(`status:${s}`, () =>
                      api.status(charger.charger_id, {
                        connector_id: connectorId,
                        status: s,
                        error_code: s === "Faulted" ? "InternalError" : "NoError",
                      })
                    )
                  }
                >
                  {s}
                </Button>
              ))}
            </div>
            <div className="flex items-center gap-2">
              <Label>Connector</Label>
              <Select
                className="w-24"
                value={connectorId}
                onChange={(e) => setConnectorId(Number(e.target.value))}
              >
                {Array.from({ length: charger.number_of_connectors }, (_, i) => i + 1).map((id) => (
                  <option key={id} value={id}>
                    {id}
                  </option>
                ))}
              </Select>
            </div>
          </section>

          {/* Transaction */}
          <section className="space-y-2 lg:col-span-2">
            <h3 className="text-sm font-semibold">Transaction</h3>
            <div className="flex flex-wrap items-end gap-2">
              <div>
                <Label>RFID Tag</Label>
                <Input value={idTag} onChange={(e) => setIdTag(e.target.value)} />
              </div>
              <Button
                disabled={!charger.connected || charger.transaction_id !== null}
                onClick={() =>
                  run("start_tx", () =>
                    api.startTransaction(charger.charger_id, {
                      connector_id: connectorId,
                      id_tag: idTag,
                      meter_start: Math.round(charger.energy_wh),
                    })
                  )
                }
              >
                <Play className="h-4 w-4" /> Start Charging
              </Button>
              <Button
                variant="destructive"
                disabled={!charger.connected || charger.transaction_id === null}
                onClick={() =>
                  run("stop_tx", () =>
                    api.stopTransaction(charger.charger_id, {
                      transaction_id: charger.transaction_id ?? 0,
                      id_tag: idTag,
                      reason: "Local",
                    })
                  )
                }
              >
                <Square className="h-4 w-4" /> Stop Charging
              </Button>
              <Button
                variant="outline"
                disabled={!charger.connected}
                onClick={() => run("authorize", () => api.authorize(charger.charger_id, idTag))}
              >
                Authorize
              </Button>
              <Button variant="outline" onClick={() => setCustomOpen(true)} disabled={!charger.connected}>
                <Send className="h-4 w-4" /> Custom Message
              </Button>
              <Button variant="outline" onClick={onDelete}>
                <Trash2 className="h-4 w-4" /> Delete Charger
              </Button>
            </div>
          </section>

          {err && (
            <div className="lg:col-span-2 text-sm text-destructive bg-destructive/10 rounded p-2">{err}</div>
          )}
        </div>

        <div className="border-t h-[400px]">
          <LogPanel chargerId={charger.charger_id} logs={logs} onClear={onLogsCleared} />
        </div>
      </CardContent>

      <CustomMessageDialog
        open={customOpen}
        onClose={() => setCustomOpen(false)}
        chargerId={charger.charger_id}
      />
    </Card>
  );
}

function CustomMessageDialog({ open, onClose, chargerId }: { open: boolean; onClose: () => void; chargerId: string }) {
  const [action, setAction] = useState("DataTransfer");
  const [payload, setPayload] = useState('{\n  "vendorId": "Trodec",\n  "messageId": "Hello",\n  "data": "Test"\n}');
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const send = async () => {
    setError(null);
    setResult(null);
    setBusy(true);
    try {
      const parsed = JSON.parse(payload);
      const r = await api.custom(chargerId, action, parsed);
      setResult(JSON.stringify(r, null, 2));
    } catch (e: any) {
      setError(e?.message || "Failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} title="Send Custom OCPP Message">
      <div className="space-y-3">
        <div>
          <Label>Action</Label>
          <Input value={action} onChange={(e) => setAction(e.target.value)} />
        </div>
        <div>
          <Label>Payload (JSON)</Label>
          <Textarea rows={10} value={payload} onChange={(e) => setPayload(e.target.value)} />
        </div>
        {error && <div className="text-sm text-destructive">{error}</div>}
        {result && (
          <div>
            <Label>Result</Label>
            <pre className="rounded bg-black/60 p-3 text-xs mono overflow-auto max-h-60">{result}</pre>
          </div>
        )}
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>
            Close
          </Button>
          <Button onClick={send} disabled={busy}>
            Send
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
