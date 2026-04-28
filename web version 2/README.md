# Chute Liner Monitor — Web Version 2

A demo UI for a vibration-based chute liner monitoring system.
Built with React + Vite + Recharts. No backend, no authentication — pure frontend with mock data.

## Features

- **Dashboard**: Liner thickness prediction banner with colour-coded wear status, thickness % over time chart with green/yellow/red zone backgrounds
- **Details**: Latest key vibration features (f₁, f₂/f₁, decay/damping/Q, spectral centroid/energy, RMS), primary resonance frequency chart, full measurement history table
- **Settings**: Real-time system clock, scheduled measurement datetime picker with live countdown, manual trigger button
- **Dark / Light theme toggle** (persisted in localStorage)

## Quick Start

```bash
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173) in your browser.

## Build

```bash
npm run build    # outputs to dist/
npm run preview  # preview the production build
```

## Stack

| Package | Version | Purpose |
|---|---|---|
| react | ^18 | UI framework |
| react-dom | ^18 | DOM rendering |
| recharts | ^2 | Charts |
| lucide-react | ^0.453 | Icons |
| vite | ^5 | Build tool |

## Project Structure

```
src/
  App.jsx                  # App shell, sidebar, tab navigation, theme toggle
  main.jsx                 # React entry point
  index.css                # Global styles (pure CSS, light + dark theme variables)
  contexts/
    ThemeContext.jsx        # Dark/light theme context with localStorage persistence
  lib/
    mockData.js             # Mock measurement history (12 sessions)
  pages/
    Dashboard.jsx           # Wear overview + thickness chart
    Details.jsx             # Key features + freq chart + history table
    SettingsPanel.jsx       # Schedule picker + manual trigger
```
