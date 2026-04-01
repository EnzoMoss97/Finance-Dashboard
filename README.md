# Billr Dashboard (HTML + SQLite + Docker)

Your dashboard UI runs as an HTML app, and now saves data in a real SQLite database instead of browser localStorage.

## Where data is stored
- **Database file:** `./data/billr.db` on your host machine.
- Inside container: `/app/data/billr.db`.

Because `docker-compose.yml` mounts `./data:/app/data`, your data persists even if you rebuild/restart containers.

## Run locally with Docker
```bash
docker compose up --build
```

Open: `http://localhost:8000`

## API used by the frontend
- `GET /api/state` → load whole dashboard state.
- `PUT /api/state` → save whole dashboard state.

The frontend keeps your existing layout and features, but storage is now server-side SQLite.
