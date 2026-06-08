# EV Charger Simulator (OCPP 1.6J)

A complete web-based OCPP 1.6 charge-point simulator. Spin up virtual EV
chargers in your browser, connect them to any OCPP CSMS (SteVe, commercial
platforms, custom servers), simulate charging sessions, and watch every OCPP
message flow in real time.

## Features

- Create unlimited virtual chargers (multi-charger support, in-memory store)
- Connect to any `ws://` or `wss://` CSMS endpoint, optional HTTP Basic Auth
- Full OCPP 1.6J wire protocol (CALL / CALLRESULT / CALLERROR over JSON)
- Outgoing messages: `BootNotification`, `Heartbeat`, `StatusNotification`,
  `Authorize`, `StartTransaction`, `StopTransaction`, `MeterValues`,
  `DataTransfer`, plus arbitrary custom actions
- Incoming command handling: `RemoteStartTransaction`, `RemoteStopTransaction`,
  `Reset` (with automatic reconnect), `ChangeAvailability`, `TriggerMessage`,
  `UnlockConnector`, `ChangeConfiguration`, `GetConfiguration`, `ClearCache`,
  `SendLocalList`, `GetLocalListVersion`, `ReserveNow`, `CancelReservation`,
  `DataTransfer`, `GetDiagnostics`, `UpdateFirmware`
- Realistic charging simulation: connector status transitions
  (`Available → Preparing → Charging → Finishing → Available`) with configurable
  power, voltage, current and accumulated `Energy.Active.Import.Register`
- Live log panel with per-message inspector, raw frame view, JSON / CSV / TXT
  export, direction filters and auto-scroll
- Manual OCPP message sender (send any custom action + JSON payload)
- Dashboard summary per charger: connection state, OCPP status, transaction id,
  energy delivered, CSMS URL
- Configurable heartbeat and meter sample interval per charger
- Realtime push to the UI over a single WebSocket; survives auto-reconnect

## Tech Stack

**Backend:** Python 3.11+ · FastAPI · `websockets` · asyncio
**Frontend:** Next.js 15 · TypeScript · Tailwind CSS · shadcn/ui-style primitives

No database required — all state is held in memory.

## Project Structure

```
ev-charger-simulator/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py        # FastAPI routes + UI websocket
│   │   ├── charger.py     # OCPP 1.6J ChargePoint simulator
│   │   ├── manager.py     # In-memory multi-charger manager
│   │   └── models.py      # Pydantic request/response models
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── app/
│   │   ├── globals.css
│   │   ├── layout.tsx
│   │   └── page.tsx       # Main dashboard
│   ├── components/
│   │   ├── ChargerPanel.tsx
│   │   ├── CreateChargerDialog.tsx
│   │   ├── LogPanel.tsx
│   │   └── ui/            # shadcn-style primitives
│   ├── lib/
│   │   ├── api.ts
│   │   └── utils.ts
│   ├── package.json
│   ├── next.config.mjs
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   └── Dockerfile
├── docker-compose.yml
└── README.md
```

## Quick Start

### Option A — Docker Compose (recommended)

```bash
docker compose up --build
```

Then open <http://localhost:3000>.

### Option B — Run locally

**Backend**

```bash
cd backend
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**Frontend**

```bash
cd frontend
npm install --legacy-peer-deps
npm run dev
```

Open <http://localhost:3000>.

## Using the Simulator

1. Click **New Charger**, enter an id like `SIM001` and details.
2. In the charger panel, set the CSMS URL (`ws://localhost:9000` for SteVe's
   default) and click **Connect**. The simulator appends `/SIM001` to the URL
   automatically and negotiates the `ocpp1.6` subprotocol.
3. `BootNotification` is sent automatically after the WebSocket opens. If the
   CSMS accepts, periodic heartbeats start at the interval the CSMS returned.
4. Use the **Status Simulation** buttons to push `StatusNotification` updates
   for any connector.
5. Enter an **RFID Tag**, then click **Start Charging**. The simulator runs
   `Authorize → StartTransaction`, transitions the connector through
   `Preparing → Charging`, and begins sending periodic `MeterValues` with
   accumulating energy. Click **Stop Charging** to issue `StopTransaction`.
6. Click any log line to open the **Message Inspector** with the parsed payload
   and raw OCPP-J frame. Export the entire log to JSON, CSV or TXT.
7. Click **Custom Message** to send any OCPP action and payload.

Incoming CSMS commands (e.g. `RemoteStartTransaction`, `Reset`, `TriggerMessage`)
are handled automatically and reflected in the UI in real time.

## OCPP Compliance Notes

The simulator implements the OCPP 1.6J wire protocol directly:

- WebSocket subprotocol: `ocpp1.6`
- Message framing: `[2, "<uuid>", "<Action>", {...}]` for `CALL`,
  `[3, "<uuid>", {...}]` for `CALLRESULT`, `[4, "<uuid>", "<errorCode>", "<errorDescription>", {...}]` for `CALLERROR`
- Timestamps in ISO-8601 UTC (`...Z`)
- Sampled values include `Energy.Active.Import.Register` (Wh),
  `Power.Active.Import` (W), `Voltage` (V) and `Current.Import` (A)

It has been validated against the open-source [SteVe](https://github.com/steve-community/steve)
CSMS and works against any compliant OCPP 1.6 server.

## REST API (backend)

All routes are mounted under `http://localhost:8000`.

| Method | Path                                            | Description                          |
|--------|-------------------------------------------------|--------------------------------------|
| GET    | `/api/health`                                   | Health probe                         |
| GET    | `/api/chargers`                                 | List chargers                        |
| POST   | `/api/chargers`                                 | Create a charger                     |
| GET    | `/api/chargers/{id}`                            | Snapshot                             |
| DELETE | `/api/chargers/{id}`                            | Delete (disconnects first)           |
| POST   | `/api/chargers/{id}/connect`                    | Connect to CSMS                      |
| POST   | `/api/chargers/{id}/disconnect`                 | Disconnect                           |
| POST   | `/api/chargers/{id}/boot`                       | Send BootNotification                |
| POST   | `/api/chargers/{id}/heartbeat`                  | Send Heartbeat                       |
| POST   | `/api/chargers/{id}/heartbeat-interval`         | Update heartbeat period              |
| POST   | `/api/chargers/{id}/status`                     | Send StatusNotification              |
| POST   | `/api/chargers/{id}/authorize`                  | Send Authorize                       |
| POST   | `/api/chargers/{id}/start-transaction`          | Authorize + StartTransaction         |
| POST   | `/api/chargers/{id}/stop-transaction`           | StopTransaction                      |
| POST   | `/api/chargers/{id}/meter-values`               | Send a single MeterValues            |
| POST   | `/api/chargers/{id}/meter-config`               | Update metering config               |
| POST   | `/api/chargers/{id}/custom`                     | Send any OCPP action                 |
| GET    | `/api/chargers/{id}/logs`                       | All log entries                      |
| DELETE | `/api/chargers/{id}/logs`                       | Clear log                            |
| GET    | `/api/chargers/{id}/logs/export?format=json…`   | Download logs (json / csv / txt)     |
| WS     | `/ws/ui`                                        | UI realtime push                     |

## Troubleshooting

- **Connection rejected by CSMS** — check the URL does *not* already include
  the charger id (the simulator appends it). Make sure the CSMS expects the
  `ocpp1.6` subprotocol.
- **`Boot accepted` is false** — your CSMS may not yet have the charge point
  registered. Register `SIM001` in the CSMS first.
- **Frontend cannot reach backend** — set `NEXT_PUBLIC_API_URL` and
  `NEXT_PUBLIC_WS_URL` environment variables when running on different hosts.

## License

MIT.
# ev-charger-simulator
