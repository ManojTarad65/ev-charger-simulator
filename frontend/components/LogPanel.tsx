"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowDownToLine, ArrowUpFromLine, Cpu, Trash2, Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Dialog } from "@/components/ui/dialog";
import { api, LogEntry } from "@/lib/api";
import { cn } from "@/lib/utils";

export function LogPanel({
  chargerId,
  logs,
  onClear,
}: {
  chargerId: string;
  logs: LogEntry[];
  onClear: () => void;
}) {
  const [filter, setFilter] = useState<"ALL" | "IN" | "OUT" | "SYS">("ALL");
  const [inspect, setInspect] = useState<LogEntry | null>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);

  const filtered = useMemo(
    () => (filter === "ALL" ? logs : logs.filter((l) => l.direction === filter)),
    [logs, filter]
  );

  useEffect(() => {
    if (autoScroll) bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [filtered.length, autoScroll]);

  const clearLogs = async () => {
    await api.clearLogs(chargerId);
    onClear();
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between border-b p-2 gap-2 flex-wrap">
        <div className="flex gap-1">
          {(["ALL", "OUT", "IN", "SYS"] as const).map((f) => (
            <Button
              key={f}
              size="sm"
              variant={filter === f ? "default" : "outline"}
              onClick={() => setFilter(f)}
            >
              {f}
            </Button>
          ))}
        </div>
        <div className="flex gap-1">
          <Button
            size="sm"
            variant={autoScroll ? "default" : "outline"}
            onClick={() => setAutoScroll((s) => !s)}
          >
            Auto-scroll
          </Button>
          <a href={api.exportLogsUrl(chargerId, "json")} target="_blank" rel="noreferrer">
            <Button size="sm" variant="outline">
              <Download className="h-3 w-3" /> JSON
            </Button>
          </a>
          <a href={api.exportLogsUrl(chargerId, "csv")} target="_blank" rel="noreferrer">
            <Button size="sm" variant="outline">
              <Download className="h-3 w-3" /> CSV
            </Button>
          </a>
          <a href={api.exportLogsUrl(chargerId, "txt")} target="_blank" rel="noreferrer">
            <Button size="sm" variant="outline">
              <Download className="h-3 w-3" /> TXT
            </Button>
          </a>
          <Button size="sm" variant="destructive" onClick={clearLogs}>
            <Trash2 className="h-3 w-3" /> Clear
          </Button>
        </div>
      </div>
      <div className="flex-1 overflow-auto p-2 mono text-xs space-y-1 bg-black/40">
        {filtered.length === 0 && (
          <div className="text-muted-foreground italic text-center py-8">No messages yet.</div>
        )}
        {filtered.map((l, i) => (
          <LogRow key={i} entry={l} onClick={() => setInspect(l)} />
        ))}
        <div ref={bottomRef} />
      </div>

      <Dialog
        open={!!inspect}
        onClose={() => setInspect(null)}
        title={
          inspect ? `${inspect.direction} ${inspect.message_type} ${inspect.action || ""}` : "Message"
        }
      >
        {inspect && (
          <div className="space-y-3">
            <div className="text-xs text-muted-foreground">{inspect.timestamp}</div>
            {inspect.message_id && (
              <div className="text-xs">
                Message ID: <span className="mono">{inspect.message_id}</span>
              </div>
            )}
            <pre className="rounded bg-black/60 p-3 text-xs mono overflow-auto max-h-[60vh]">
              {JSON.stringify(inspect.payload, null, 2)}
            </pre>
            {inspect.raw && (
              <details>
                <summary className="cursor-pointer text-xs text-muted-foreground">Raw OCPP-J Frame</summary>
                <pre className="mt-2 rounded bg-black/60 p-3 text-xs mono overflow-auto max-h-[40vh]">
                  {inspect.raw}
                </pre>
              </details>
            )}
          </div>
        )}
      </Dialog>
    </div>
  );
}

function LogRow({ entry, onClick }: { entry: LogEntry; onClick: () => void }) {
  const arrow =
    entry.direction === "OUT" ? (
      <ArrowUpFromLine className="h-3 w-3 text-emerald-400" />
    ) : entry.direction === "IN" ? (
      <ArrowDownToLine className="h-3 w-3 text-sky-400" />
    ) : (
      <Cpu className="h-3 w-3 text-amber-400" />
    );
  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full text-left px-2 py-1 rounded hover:bg-white/5 flex items-center gap-2",
        entry.message_type === "CALLERROR" && "bg-red-950/40"
      )}
    >
      <span className="text-muted-foreground tabular-nums">{entry.timestamp.split("T")[1]?.replace("Z", "")}</span>
      {arrow}
      <Badge variant={entry.direction === "OUT" ? "success" : entry.direction === "IN" ? "info" : "warning"}>
        {entry.message_type}
      </Badge>
      <span className="font-medium">{entry.action || "-"}</span>
      <span className="text-muted-foreground truncate">
        {typeof entry.payload === "object" ? JSON.stringify(entry.payload) : String(entry.payload ?? "")}
      </span>
    </button>
  );
}
