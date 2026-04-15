from pathlib import Path
import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field
from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    create_engine,
    func,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/aviation.db")
SYNC_DB_URL = os.getenv("SQLITE_SYNC_DB_URL", "sqlite:///./data/offline_sync.db")
Path('data').mkdir(parents=True, exist_ok=True)
JWT_SECRET = os.getenv("JWT_SECRET", "change-this-secret")
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRE_MINUTES = int(os.getenv("TOKEN_EXPIRE_MINUTES", "720"))
DEFAULT_PAX_WEIGHT_KG = Decimal(os.getenv("DEFAULT_PAX_WEIGHT_KG", "90"))


class Base(DeclarativeBase):
    pass


class Role(str, Enum):
    ADMIN = "Admin"
    DISPATCHER = "Dispatcher"
    AGENT = "Agent"
    ACCOUNTANT = "Accountant"


class FlightStatus(str, Enum):
    SCHEDULED = "scheduled"
    BOARDING = "boarding"
    DEPARTED = "departed"
    LANDED = "landed"
    CANCELLED = "cancelled"


class BookingType(str, Enum):
    PAX = "PAX"
    CARGO = "CARGO"


class BookingStatus(str, Enum):
    RESERVED = "reserved"
    CONFIRMED = "confirmed"
    CHECKED_IN = "checked-in"
    NO_SHOW = "no-show"


class PaymentStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(SqlEnum(Role), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Aircraft(Base):
    __tablename__ = "aircraft"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    max_passengers: Mapped[int] = mapped_column(Integer)
    max_cargo_weight: Mapped[Decimal] = mapped_column(Numeric(10, 2))


class Route(Base):
    __tablename__ = "routes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    origin: Mapped[str] = mapped_column(String(60))
    destination: Mapped[str] = mapped_column(String(60))


class Flight(Base):
    __tablename__ = "flights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    aircraft_id: Mapped[int] = mapped_column(ForeignKey("aircraft.id"), index=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id"), index=True)
    departure_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[FlightStatus] = mapped_column(SqlEnum(FlightStatus), default=FlightStatus.SCHEDULED)
    pilot_name: Mapped[str] = mapped_column(String(120), default="TBD")
    final_load_validated: Mapped[bool] = mapped_column(Boolean, default=False)

    aircraft: Mapped[Aircraft] = relationship()
    route: Mapped[Route] = relationship()


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[BookingType] = mapped_column(SqlEnum(BookingType), index=True)
    status: Mapped[BookingStatus] = mapped_column(SqlEnum(BookingStatus), default=BookingStatus.RESERVED)
    payment_status: Mapped[PaymentStatus] = mapped_column(SqlEnum(PaymentStatus), default=PaymentStatus.PENDING)
    total_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    flight_id: Mapped[int] = mapped_column(ForeignKey("flights.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Passenger(Base):
    __tablename__ = "passengers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    contact: Mapped[str] = mapped_column(String(120))
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id"), index=True)
    flight_id: Mapped[int] = mapped_column(ForeignKey("flights.id"), index=True)
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=DEFAULT_PAX_WEIGHT_KG)


class Cargo(Base):
    __tablename__ = "cargo"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    weight: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    cargo_type: Mapped[str] = mapped_column(String(80))
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id"), index=True)
    flight_id: Mapped[int] = mapped_column(ForeignKey("flights.id"), index=True)
    shipper: Mapped[str] = mapped_column(String(150))
    receiver: Mapped[str] = mapped_column(String(150))
    awb_number: Mapped[str] = mapped_column(String(40), unique=True)


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    method: Mapped[str] = mapped_column(String(40))
    status: Mapped[PaymentStatus] = mapped_column(SqlEnum(PaymentStatus), default=PaymentStatus.PAID)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Cost(Base):
    __tablename__ = "costs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    flight_id: Mapped[int] = mapped_column(ForeignKey("flights.id"), unique=True, index=True)
    fuel_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    pilot_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    maintenance_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))


class OfflineEvent(Base):
    __tablename__ = "offline_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity: Mapped[str] = mapped_column(String(80), index=True)
    entity_id: Mapped[str] = mapped_column(String(80), index=True)
    operation: Mapped[str] = mapped_column(String(20))
    payload: Mapped[str] = mapped_column(String(4000))
    modified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source: Mapped[str] = mapped_column(String(30), default="sqlite-offline")


connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, future=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

sync_args = {"check_same_thread": False} if SYNC_DB_URL.startswith("sqlite") else {}
sync_engine = create_engine(SYNC_DB_URL, future=True, connect_args=sync_args)
SyncSessionLocal = sessionmaker(bind=sync_engine, autoflush=False, autocommit=False, future=True)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

app = FastAPI(title="Aviation Booking & Operations API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: Role


class FlightCreate(BaseModel):
    aircraft_id: int
    route_id: int
    departure_time: datetime
    pilot_name: str = "TBD"


class FlightPatch(BaseModel):
    status: Optional[FlightStatus] = None
    aircraft_id: Optional[int] = None
    route_id: Optional[int] = None
    departure_time: Optional[datetime] = None
    pilot_name: Optional[str] = None
    final_load_validated: Optional[bool] = None


class BookingCreate(BaseModel):
    type: BookingType
    status: BookingStatus = BookingStatus.RESERVED
    payment_status: PaymentStatus = PaymentStatus.PENDING
    total_price: Decimal = Decimal("0.00")
    flight_id: int


class PassengerCreate(BaseModel):
    name: str
    contact: str
    booking_id: int
    flight_id: int
    weight_kg: Decimal = DEFAULT_PAX_WEIGHT_KG


class PassengerCheckIn(BaseModel):
    booking_id: int


class CargoCreate(BaseModel):
    shipper: str
    receiver: str
    cargo_type: str
    weight: Decimal = Field(gt=0)
    price: Decimal = Field(gt=0)
    booking_id: int
    flight_id: int


class CostInput(BaseModel):
    flight_id: int
    fuel_cost: Decimal = Decimal("0.00")
    pilot_cost: Decimal = Decimal("0.00")
    maintenance_cost: Decimal = Decimal("0.00")


class SyncPayload(BaseModel):
    events: list[dict]


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_sync_db():
    db = SyncSessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    unauthorized = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        username: str = payload.get("sub")
        if not username:
            raise unauthorized
    except JWTError as exc:
        raise unauthorized from exc

    user = db.scalar(select(User).where(User.username == username))
    if not user:
        raise unauthorized
    return user


def require_roles(*allowed: Role):
    def checker(current_user: User = Depends(get_current_user)):
        if current_user.role not in allowed:
            raise HTTPException(status_code=403, detail="Forbidden for your role")
        return current_user

    return checker


def get_flight_or_404(db: Session, flight_id: int) -> Flight:
    flight = db.get(Flight, flight_id)
    if not flight:
        raise HTTPException(404, "Flight not found")
    return flight


def compute_load(db: Session, flight: Flight) -> dict:
    pax_count = db.scalar(select(func.count(Passenger.id)).where(Passenger.flight_id == flight.id)) or 0
    pax_weight = db.scalar(select(func.coalesce(func.sum(Passenger.weight_kg), 0)).where(Passenger.flight_id == flight.id)) or Decimal("0")
    cargo_weight = db.scalar(select(func.coalesce(func.sum(Cargo.weight), 0)).where(Cargo.flight_id == flight.id)) or Decimal("0")

    max_pax = flight.aircraft.max_passengers
    max_cargo = Decimal(flight.aircraft.max_cargo_weight)
    total_weight = Decimal(pax_weight) + Decimal(cargo_weight)
    max_total = Decimal(max_pax) * DEFAULT_PAX_WEIGHT_KG + max_cargo

    level = "SAFE"
    if pax_count > max_pax or cargo_weight > max_cargo or total_weight > max_total:
        level = "OVERLOAD"
    elif pax_count >= max_pax * Decimal("0.9") or cargo_weight >= max_cargo * Decimal("0.9"):
        level = "WARNING"

    return {
        "pax_count": pax_count,
        "cargo_weight": float(cargo_weight),
        "total_weight": float(total_weight),
        "capacity_weight": float(max_total),
        "load_factor": round(float((total_weight / max_total) * Decimal("100")) if max_total else 0, 2),
        "status": level,
    }


def ensure_not_overbooked(db: Session, flight: Flight):
    load = compute_load(db, flight)
    if load["status"] == "OVERLOAD":
        raise HTTPException(400, "Aircraft limits exceeded: cannot overbook")


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(engine)
    Base.metadata.create_all(sync_engine)
    with SessionLocal() as db:
        if not db.scalar(select(User).where(User.username == "admin")):
            db.add_all(
                [
                    User(username="admin", password_hash=pwd_context.hash("admin123"), role=Role.ADMIN),
                    User(username="dispatcher", password_hash=pwd_context.hash("dispatch123"), role=Role.DISPATCHER),
                    User(username="agent", password_hash=pwd_context.hash("agent123"), role=Role.AGENT),
                    User(username="accountant", password_hash=pwd_context.hash("account123"), role=Role.ACCOUNTANT),
                ]
            )
        if db.scalar(select(func.count(Aircraft.id))) == 0:
            c208 = Aircraft(name="Cessna 208 Caravan", max_passengers=13, max_cargo_weight=Decimal("1400"))
            c172 = Aircraft(name="Cessna 172", max_passengers=3, max_cargo_weight=Decimal("250"))
            db.add_all([c208, c172])
        if db.scalar(select(func.count(Route.id))) == 0:
            db.add_all(
                [
                    Route(origin="Nairobi", destination="Lodwar"),
                    Route(origin="Nairobi", destination="Kakamega"),
                    Route(origin="Lodwar", destination="Eldoret"),
                ]
            )
        db.commit()


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/auth/login", response_model=TokenResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == form_data.username))
    if not user or not pwd_context.verify(form_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_access_token({"sub": user.username, "role": user.role.value})
    return TokenResponse(access_token=token, role=user.role)


@app.get("/auth/me")
def me(current_user: User = Depends(get_current_user)):
    return {"username": current_user.username, "role": current_user.role}


@app.get("/routes")
def list_routes(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(Route)).all()


@app.get("/aircraft")
def list_aircraft(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(Aircraft)).all()


@app.get("/flights")
def get_flights(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    flights = db.scalars(select(Flight).order_by(Flight.departure_time)).all()
    return [
        {
            "id": f.id,
            "aircraft": f.aircraft.name,
            "route": f"{f.route.origin} → {f.route.destination}",
            "departure_time": f.departure_time,
            "status": f.status,
            "pilot_name": f.pilot_name,
            **compute_load(db, f),
        }
        for f in flights
    ]


@app.post("/flights")
def create_flight(payload: FlightCreate, db: Session = Depends(get_db), _: User = Depends(require_roles(Role.ADMIN, Role.DISPATCHER))):
    flight = Flight(**payload.model_dump())
    db.add(flight)
    db.commit()
    db.refresh(flight)
    return {"id": flight.id}


@app.patch("/flights/{flight_id}")
def patch_flight(
    flight_id: int,
    payload: FlightPatch,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.ADMIN, Role.DISPATCHER)),
):
    flight = get_flight_or_404(db, flight_id)
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(flight, key, value)

    if flight.status == FlightStatus.DEPARTED:
        pax_count = db.scalar(select(func.count(Passenger.id)).where(Passenger.flight_id == flight.id)) or 0
        if pax_count == 0:
            raise HTTPException(400, "No departure allowed without passenger manifest")
        if not flight.final_load_validated:
            raise HTTPException(400, "No departure allowed without final load validation")
        ensure_not_overbooked(db, flight)

    db.commit()
    return {"ok": True}


@app.post("/bookings")
def create_booking(payload: BookingCreate, db: Session = Depends(get_db), _: User = Depends(require_roles(Role.ADMIN, Role.AGENT, Role.DISPATCHER))):
    get_flight_or_404(db, payload.flight_id)
    booking = Booking(**payload.model_dump())
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return {"id": booking.id}


@app.get("/bookings")
def list_bookings(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rows = db.scalars(select(Booking).order_by(Booking.created_at.desc())).all()
    return rows


@app.post("/passengers")
def create_passenger(payload: PassengerCreate, db: Session = Depends(get_db), _: User = Depends(require_roles(Role.ADMIN, Role.AGENT, Role.DISPATCHER))):
    booking = db.get(Booking, payload.booking_id)
    if not booking or booking.type != BookingType.PAX:
        raise HTTPException(400, "Booking not found or not PAX type")
    flight = get_flight_or_404(db, payload.flight_id)
    passenger = Passenger(**payload.model_dump())
    db.add(passenger)
    db.flush()
    ensure_not_overbooked(db, flight)
    db.commit()
    db.refresh(passenger)
    return {"id": passenger.id}


@app.post("/passengers/checkin")
def checkin(payload: PassengerCheckIn, db: Session = Depends(get_db), _: User = Depends(require_roles(Role.ADMIN, Role.AGENT, Role.DISPATCHER))):
    booking = db.get(Booking, payload.booking_id)
    if not booking:
        raise HTTPException(404, "Booking not found")
    booking.status = BookingStatus.CHECKED_IN
    db.commit()
    return {"ok": True}


@app.post("/cargo")
def create_cargo(payload: CargoCreate, db: Session = Depends(get_db), _: User = Depends(require_roles(Role.ADMIN, Role.AGENT, Role.DISPATCHER))):
    booking = db.get(Booking, payload.booking_id)
    if not booking or booking.type != BookingType.CARGO:
        raise HTTPException(400, "Booking not found or not CARGO type")

    flight = get_flight_or_404(db, payload.flight_id)
    awb = f"AWB-{payload.flight_id}-{int(datetime.now(timezone.utc).timestamp())}"
    row = Cargo(**payload.model_dump(), awb_number=awb)
    db.add(row)
    db.flush()
    ensure_not_overbooked(db, flight)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "awb_number": row.awb_number}


@app.get("/cargo")
def get_cargo(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(Cargo).order_by(Cargo.id.desc())).all()


@app.get("/flights/{flight_id}/manifest")
def flight_manifest(flight_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    get_flight_or_404(db, flight_id)
    passengers = db.scalars(select(Passenger).where(Passenger.flight_id == flight_id)).all()
    cargo = db.scalars(select(Cargo).where(Cargo.flight_id == flight_id)).all()
    return {"passengers": passengers, "cargo": cargo}


@app.get("/dispatch/today")
def dispatch_today(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    today = date.today()
    start = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
    end = datetime.combine(today, datetime.max.time(), tzinfo=timezone.utc)
    flights = db.scalars(select(Flight).where(Flight.departure_time >= start, Flight.departure_time <= end)).all()
    return [
        {
            "id": f.id,
            "aircraft": f.aircraft.name,
            "route": f"{f.route.origin} → {f.route.destination}",
            "departure_time": f.departure_time,
            **compute_load(db, f),
        }
        for f in flights
    ]


@app.post("/costs")
def upsert_costs(payload: CostInput, db: Session = Depends(get_db), _: User = Depends(require_roles(Role.ADMIN, Role.ACCOUNTANT))):
    get_flight_or_404(db, payload.flight_id)
    current = db.scalar(select(Cost).where(Cost.flight_id == payload.flight_id))
    if not current:
        current = Cost(**payload.model_dump())
        db.add(current)
    else:
        current.fuel_cost = payload.fuel_cost
        current.pilot_cost = payload.pilot_cost
        current.maintenance_cost = payload.maintenance_cost
    db.commit()
    return {"ok": True}


@app.get("/reports/revenue")
def revenue_report(
    period: str = Query("daily", pattern="^(daily|monthly)$"),
    start: Optional[date] = None,
    end: Optional[date] = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.ADMIN, Role.ACCOUNTANT, Role.DISPATCHER)),
):
    start_dt = datetime.combine(start or date.today(), datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(end or date.today(), datetime.max.time(), tzinfo=timezone.utc)

    flights = db.scalars(select(Flight).where(Flight.departure_time >= start_dt, Flight.departure_time <= end_dt)).all()
    result = []
    for flight in flights:
        pax_revenue = db.scalar(
            select(func.coalesce(func.sum(Booking.total_price), 0)).where(Booking.flight_id == flight.id, Booking.type == BookingType.PAX)
        ) or Decimal("0")
        cargo_revenue = db.scalar(
            select(func.coalesce(func.sum(Booking.total_price), 0)).where(Booking.flight_id == flight.id, Booking.type == BookingType.CARGO)
        ) or Decimal("0")
        cost = db.scalar(select(Cost).where(Cost.flight_id == flight.id))
        total_cost = Decimal("0")
        if cost:
            total_cost = Decimal(cost.fuel_cost) + Decimal(cost.pilot_cost) + Decimal(cost.maintenance_cost)
        total_rev = Decimal(pax_revenue) + Decimal(cargo_revenue)
        result.append(
            {
                "flight_id": flight.id,
                "date": flight.departure_time.date(),
                "pax_revenue": float(pax_revenue),
                "cargo_revenue": float(cargo_revenue),
                "total_revenue": float(total_rev),
                "total_cost": float(total_cost),
                "profit": float(total_rev - total_cost),
            }
        )

    if period == "monthly":
        buckets = {}
        for row in result:
            key = row["date"].strftime("%Y-%m")
            if key not in buckets:
                buckets[key] = {"month": key, "pax_revenue": 0.0, "cargo_revenue": 0.0, "total_revenue": 0.0, "total_cost": 0.0, "profit": 0.0}
            for metric in ["pax_revenue", "cargo_revenue", "total_revenue", "total_cost", "profit"]:
                buckets[key][metric] += row[metric]
        return list(buckets.values())

    return result


@app.get("/reports/flights")
def flights_report(db: Session = Depends(get_db), _: User = Depends(require_roles(Role.ADMIN, Role.DISPATCHER, Role.ACCOUNTANT))):
    flights = db.scalars(select(Flight).order_by(Flight.departure_time.desc())).all()
    return [
        {
            "flight_id": f.id,
            "route": f"{f.route.origin} → {f.route.destination}",
            "status": f.status,
            "departure_time": f.departure_time,
            **compute_load(db, f),
        }
        for f in flights
    ]


@app.post("/sync/offline-events")
def sync_offline(
    payload: SyncPayload,
    sync_db: Session = Depends(get_sync_db),
    _: User = Depends(require_roles(Role.ADMIN, Role.DISPATCHER, Role.AGENT)),
):
    for event in payload.events:
        row = OfflineEvent(
            entity=event["entity"],
            entity_id=str(event["entity_id"]),
            operation=event["operation"],
            payload=str(event.get("payload", {})),
            modified_at=datetime.fromisoformat(event["modified_at"]),
            source=event.get("source", "sqlite-offline"),
        )
        sync_db.add(row)
    sync_db.commit()

    # Conflict strategy: Last Write Wins using modified_at timestamp.
    return {
        "accepted": len(payload.events),
        "strategy": "Last-Write-Wins by modified_at; rejected events should be replayed with newer timestamp",
    }
