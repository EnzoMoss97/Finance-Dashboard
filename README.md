# Billr Dashboard (with Login, SQLite, PDF Invoices)

## What changed
- Added login lock (session-based authentication).
- Fixed all navigation tabs so Dashboard / Log / Projects / Clients / Invoices are connected and render properly.
- Added real invoice PDF generation endpoint and download button.
- Added freelancer-focused extras:
  - monthly income goal tracking
  - CSV export for logs
  - project-linked work logs

## Default login
- Username: `admin`
- Password: `admin123`

You can override at startup with env vars:
- `APP_USERNAME`
- `APP_PASSWORD`
- `APP_SECRET`

## Data storage
- SQLite file on host: `./data/billr.db`
- In container: `/app/data/billr.db`

## Run with Docker
```bash
docker compose up --build
```

Open: `http://localhost:2555`

## API
- `POST /api/login`
- `POST /api/logout`
- `GET /api/me`
- `GET /api/state`
- `PUT /api/state`
- `GET /api/invoices/<invoice_id>/pdf`
