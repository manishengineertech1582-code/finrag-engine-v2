# Frontend

This directory contains the React + Vite frontend for FinRAG Engine v2.

For the full product overview, architecture, backend API, and demo flow, use the root [README](../README.md).

## Local development

```bash
npm install
cp .env.example .env.local
npm run dev
```

The frontend runs on `http://127.0.0.1:5173` and proxies `/api` and `/health` to the FastAPI backend on `http://127.0.0.1:8000`.

## Key directories

- `src/features/` for page-level flows such as auth, ingestion, and query
- `src/components/` for shared UI and display components
- `src/lib/` for the API client, hooks, and utilities
- `src/state/` for persisted Zustand stores

## Build

```bash
npm run build
```

The production build is written to `frontend/dist/`.
