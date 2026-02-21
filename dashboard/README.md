# Robot Buddy Dashboard

Web dashboard for the Robot Buddy supervisor. Replaces the old single-file HTML dashboard entirely — `npm run build` outputs to `supervisor_v2/static/` which FastAPI serves at `/`.

## Quick Start

### Development (with hot reload)

```bash
cd dashboard
npm install
npm run dev
```

Opens at `http://localhost:5173/`. Vite proxies all API/WS calls to the Pi at `192.168.55.100:8080` (configured in `vite.config.ts`).

### Production Build

```bash
cd dashboard
npm run build
```

Outputs to `../supervisor_v2/static/`. The supervisor serves it automatically — no separate web server needed.

## Tabs

| Tab | What it does |
|---|---|
| **Drive** | Joystick (touch + mouse), mode buttons (IDLE/TELEOP/WANDER), E-STOP, sparkline gauge cards (speeds, gyro, range, battery, tick dt), fault badges, speed caps, video feed toggle |
| **Telemetry** | 4 uPlot time-series charts (wheel speeds, rotation, range, battery) with adjustable window (30s/60s/120s) and pause/resume |
| **Devices** | Reflex/Face MCU cards (packet counts, seq, age), clock sync (offset, RTT, drift), transport stats. Polled at 2s via `/debug/devices` + `/debug/clocks` |
| **Logs** | Live log stream via `WS /ws/logs`. Virtualized list (react-window, 5000 entries). Level filter buttons, text search, pin-to-bottom auto-scroll, click-to-expand detail panel |
| **Calibration** | PID tuner (kV, kS, Kp, Ki, K_yaw + rate limits), Vision/HSV sliders, Range thresholds, IMU panel. Debounced 150ms with Apply for batch updates |
| **Parameters** | AG Grid table of all params. Grouped by owner, quick filter search, inline edit with debounced POST, safety badges |
| **Face** | Mood/intensity/gaze/brightness, 13 gesture buttons, system mode, talking + energy, 7 flag toggles, manual lock |

## Tech Stack

| Concern | Library |
|---|---|
| Framework | React 19 + TypeScript |
| Build | Vite 7 |
| State | Zustand 5 |
| Data fetching | React Query 5 (debug endpoints, params) |
| Charts | uPlot (imperative, ~35 KB, bypasses React for 20 Hz data) |
| Tables | AG Grid Community 35 (params) |
| Virtualized lists | react-window 2 (log viewer) |
| Styling | CSS Modules (dark theme) |

## Architecture

### Data Flow

```
Pi supervisor (50 Hz tick loop)
  └─ WS /ws ──── 20 Hz telemetry JSON ────► wsManager.ts ──► telemetryStore (Zustand)
  └─ WS /ws/logs ── log entries JSON ──────► wsLogs.ts ────► logStore (Zustand)
  └─ REST /debug/* ── polled 2s ───────────► React Query ──► DevicesTab / ClocksTab
  └─ REST /params ── on demand ────────────► React Query ──► ParamsTab (AG Grid)
```

### Key Design Decisions

- **Float64Array ring buffers** — 1200 samples per metric (60s @ 20Hz), zero GC pressure during ingestion
- **Charts bypass React** — uPlot updates via `zustand.subscribe()` at 5 Hz, no React reconciliation
- **Gauges throttled to 10 Hz** — `useTelemetry(selector, 100)` hook with `useSyncExternalStore`
- **Joystick uses throttle (not debounce)** — steady 10 Hz while dragging, immediate `{v:0, w:0}` on release
- **WebSocket reconnect with exponential backoff** — 0.5s to 8s cap, `ws_connected` only after first valid telemetry
- **Page Visibility API** — ring buffers keep filling when tab is backgrounded, charts force redraw on foreground return
- **Cache headers** — `index.html` served with `no-cache`; hashed asset filenames are safe to cache forever

## Project Structure

```
dashboard/
├── src/
│   ├── App.tsx                    # Tab layout, WS lifecycle
│   ├── types.ts                   # All TypeScript interfaces
│   ├── constants.ts               # Faults, moods, gestures, face flags
│   ├── stores/
│   │   ├── telemetryStore.ts      # Snapshot + ring buffers + WS meta
│   │   └── uiStore.ts            # Active tab, video toggle
│   ├── lib/
│   │   ├── ringBuffer.ts         # Float64Array circular buffer
│   │   ├── wsManager.ts          # WS with reconnect + backoff
│   │   ├── wsLogs.ts             # Log WS + log store
│   │   ├── throttle.ts           # Joystick throttle
│   │   └── debounce.ts           # Slider/param debounce
│   ├── hooks/
│   │   ├── useTelemetry.ts       # Throttled selector
│   │   ├── useWsMeta.ts          # WS health (age, gaps, reconnects)
│   │   ├── useSend.ts            # WS command sender
│   │   ├── useDevices.ts         # React Query: /debug/devices
│   │   ├── useClocks.ts          # React Query: /debug/clocks
│   │   └── useParams.ts          # React Query: /params GET + POST
│   ├── components/
│   │   ├── Header.tsx            # WS status, telemetry age, faults
│   │   ├── TabBar.tsx            # 7-tab navigation
│   │   ├── Sparkline.tsx         # Tiny uPlot (transient updates)
│   │   ├── TimeSeriesChart.tsx   # Full uPlot (transient updates)
│   │   ├── Joystick.tsx          # Canvas, touch + mouse
│   │   └── FaultBadges.tsx       # Decoded fault flags
│   ├── tabs/                     # One file per tab
│   └── styles/                   # CSS Modules (dark theme)
├── vite.config.ts                # Build → ../supervisor_v2/static/
└── package.json
```

## Scripts

```bash
npm run dev          # Vite dev server with HMR + proxy to Pi
npm run build        # TypeScript check + production build
npm run typecheck    # TypeScript only (no emit)
npm run lint         # Biome lint
npm run lint:fix     # Biome lint + autofix
npm run format       # Biome format
npm run test         # Vitest
npm run preview      # Preview production build locally
```
