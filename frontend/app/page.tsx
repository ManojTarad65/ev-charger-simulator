"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Plus, RefreshCw, Activity, Wifi, WifiOff, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { CreateChargerDialog } from "@/components/CreateChargerDialog";
import { ChargerPanel } from "@/components/ChargerPanel";
import { api, Charger, LogEntry, WS_URL } from "@/lib/api";

export default function Home() {
  const [chargers, setChargers] = useState<Record<string, Charger>>({});
  const [logs, setLogs] = useState<Record<string, LogEntry[]>>({});
  const [selected, setSelected] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [wsConnected, setWsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  const refresh = useCallback(async () => {
    const list = await api.listChargers();
    const map: Record<string, Charger> = {};
    list.forEach((c) => (map[c.charger_id] = c));
    setChargers(map);
    if (!selected && list.length) setSelected(list[0].charger_id);
    if (selected && !map[selected]) setSelected(list[0]?.charger_id ?? null);
  }, [selected]);

  const refreshLogs = useCallback(async (id: string) => {
    try {
      const entries = await api.getLogs(id);
      setLogs((prev) => ({ ...prev, [id]: entries }));
    } catch {}
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    if (selected && !logs[selected]) refreshLogs(selected);
  }, [selected, logs, refreshLogs]);

  // Realtime WebSocket
  useEffect(() => {
    let cancelled = false;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;

    const open = () => {
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;
      ws.onopen = () => setWsConnected(true);
      ws.onclose = () => {
        setWsConnected(false);
        if (!cancelled) retryTimer = setTimeout(open, 2000);
      };
      ws.onerror = () => ws.close();
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          handleWsMessage(msg.event, msg.data);
        } catch {}
      };
    };
    open();
    return () => {
      cancelled = true;
      if (retryTimer) clearTimeout(retryTimer);
      wsRef.current?.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleWsMessage = (event: string, data: any) => {
    if (event === "snapshot") {
      const map: Record<string, Charger> = {};
      (data.chargers as Charger[]).forEach((c) => (map[c.charger_id] = c));
      setChargers(map);
    } else if (event === "state") {
      setChargers((prev) => ({ ...prev, [data.charger_id]: data.state }));
    } else if (event === "charger_created") {
      setChargers((prev) => ({ ...prev, [data.charger_id]: data.state }));
    } else if (event === "charger_deleted") {
      setChargers((prev) => {
        const next = { ...prev };
        delete next[data.charger_id];
        return next;
      });
      setLogs((prev) => {
        const next = { ...prev };
        delete next[data.charger_id];
        return next;
      });
    } else if (event === "log") {
      const id = data.charger_id;
      const entry = data.entry as LogEntry;
      setLogs((prev) => {
        const cur = prev[id] || [];
        const next = [...cur, entry];
        if (next.length > 1000) next.splice(0, next.length - 1000);
        return { ...prev, [id]: next };
      });
    }
  };

  const list = useMemo(() => Object.values(chargers).sort((a, b) => a.charger_id.localeCompare(b.charger_id)), [chargers]);
  const current = selected ? chargers[selected] : null;
  const currentLogs = selected ? logs[selected] || [] : [];

  const deleteCharger = async (id: string) => {
    if (!confirm(`Delete charger ${id}?`)) return;
    await api.deleteCharger(id);
  };

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b">
        <div className="container flex items-center justify-between py-3">
          <div className="flex items-center gap-3">
            <div className="rounded-md bg-primary/20 p-2">
              <Zap className="h-5 w-5 text-primary" />
            </div>
            <div>
              <div className="font-bold text-lg leading-tight">EV Charger Simulator</div>
              <div className="text-xs text-muted-foreground">OCPP 1.6J · Connect to any CSMS</div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant={wsConnected ? "success" : "destructive"}>
              {wsConnected ? <Wifi className="h-3 w-3" /> : <WifiOff className="h-3 w-3" />}
              {wsConnected ? "LIVE" : "OFFLINE"}
            </Badge>
            <Button variant="outline" size="sm" onClick={refresh}>
              <RefreshCw className="h-4 w-4" /> Refresh
            </Button>
            <Button size="sm" onClick={() => setCreateOpen(true)}>
              <Plus className="h-4 w-4" /> New Charger
            </Button>
          </div>
        </div>
      </header>

      <main className="container py-4 grid grid-cols-1 lg:grid-cols-[260px_1fr] gap-4">
        <aside className="space-y-2">
          <div className="text-xs font-semibold text-muted-foreground uppercase">Chargers ({list.length})</div>
          {list.length === 0 && (
            <Card>
              <CardContent className="p-3 text-sm text-muted-foreground">
                No chargers yet. Click <strong>New Charger</strong> to create one.
              </CardContent>
            </Card>
          )}
          {list.map((c) => (
            <button
              key={c.charger_id}
              onClick={() => setSelected(c.charger_id)}
              className={`w-full text-left rounded-md border p-2.5 transition-colors ${
                selected === c.charger_id ? "bg-accent border-primary" : "hover:bg-accent/50"
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="font-semibold text-sm">{c.charger_id}</span>
                <Badge variant={c.connected ? "success" : "secondary"}>
                  {c.connected ? "ON" : "OFF"}
                </Badge>
              </div>
              <div className="text-[11px] text-muted-foreground mt-1 flex items-center gap-1">
                <Activity className="h-3 w-3" /> {c.status}
                {c.transaction_id !== null && ` · TX #${c.transaction_id}`}
              </div>
              <div className="text-[11px] text-muted-foreground tabular-nums">
                {(c.energy_wh / 1000).toFixed(3)} kWh
              </div>
            </button>
          ))}
        </aside>

        <section>
          {current ? (
            <ChargerPanel
              charger={current}
              logs={currentLogs}
              onRefresh={() => refresh()}
              onDelete={() => deleteCharger(current.charger_id)}
              onLogsCleared={() => setLogs((p) => ({ ...p, [current.charger_id]: [] }))}
            />
          ) : (
            <Card>
              <CardContent className="p-10 text-center text-muted-foreground">
                Select or create a charger to begin.
              </CardContent>
            </Card>
          )}
        </section>
      </main>

      <CreateChargerDialog open={createOpen} onClose={() => setCreateOpen(false)} onCreated={refresh} />
    </div>
  );
}
