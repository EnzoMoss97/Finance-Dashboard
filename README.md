# Aviation Booking & Operations System

Production-oriented web system for a small interior-flight operator handling both passenger (PAX) and cargo operations.

## Stack
- **Backend**: FastAPI (REST), SQLAlchemy, JWT auth, RBAC.
- **Frontend**: Mobile-friendly admin dashboard (HTML/JS) optimized for field agents and dispatch.
- **Databases**: PostgreSQL (primary), SQLite (offline event sync store).
- **Deployment**: Docker Compose with PostgreSQL + backend + Nginx reverse proxy with HTTPS.

## Modules Included
- Flight operations (schedule flights, assign aircraft/pilot, status updates).
- Passenger booking and check-in.
- Cargo booking with AWB generation.
- Load control combining PAX + cargo with overload prevention.
- Dispatch dashboard with SAFE/WARNING/OVERLOAD indicators.
- Accounting/reporting: per-flight revenue, daily/monthly aggregation, profit calculation with manual costs.
- Offline support endpoint and conflict strategy (Last-Write-Wins by `modified_at`).

## Default Users
| Username | Password | Role |
|---|---|---|
| admin | admin123 | Admin |
| dispatcher | dispatch123 | Dispatcher |
| agent | agent123 | Agent |
| accountant | account123 | Accountant |

## Required Endpoints
- `GET /flights`
- `POST /flights`
- `PATCH /flights/{id}`
- `POST /bookings`
- `GET /bookings`
- `POST /passengers/checkin`
- `POST /cargo`
- `GET /cargo`
- `GET /reports/revenue`
- `GET /reports/flights`

Additional useful endpoints: `/auth/login`, `/dispatch/today`, `/flights/{id}/manifest`, `/costs`, `/sync/offline-events`, `/routes`, `/aircraft`.

## Run (Docker)
1. Generate SSL cert files for local/dev use and place them in `nginx/certs/`:
   - `fullchain.pem`
   - `privkey.pem`
2. Start services:
   ```bash
   docker compose up --build
   ```
3. Open frontend at `https://localhost`.
4. API docs (Swagger): `https://localhost/api/docs`.

## Local API Run (without Docker)
```bash
pip install -r requirements.txt
uvicorn backend.main:app --reload
```
Then open `http://127.0.0.1:8000/docs`.

## Database Design
Normalized PostgreSQL DDL is provided in `sql/schema.sql`. Seed starter data in `sql/seed.sql`.

## Business Rules Enforced
- Passenger count cannot exceed aircraft seat capacity.
- Cargo weight cannot exceed aircraft cargo capacity.
- Combined load checks generate SAFE/WARNING/OVERLOAD.
- Departures blocked unless passenger manifest exists and final load is validated.

## Offline Strategy
- Remote airstrips can persist local transactions to SQLite.
- Sync through `POST /sync/offline-events` with replay events.
- Conflict resolution strategy: **Last-Write-Wins** (server applies newest `modified_at`).
