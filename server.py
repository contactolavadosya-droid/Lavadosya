from fastapi import FastAPI, APIRouter, HTTPException
from fastapi.encoders import jsonable_encoder
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

app = FastAPI(title="LAVADOSYA! API")
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("lavadosya")


# ---------- Models ----------
VEHICLE_TYPES = {
    "car": {"id": "car", "label": "Auto chico / Sedán", "multiplier": 1.0},
    "suv": {"id": "suv", "label": "Pickup mediana / SUV", "multiplier": 1.35},
    "large": {"id": "large", "label": "Vehículo grande / Van", "multiplier": 1.7},
}

STATUS_FLOW = ["pendiente", "aceptado", "en_camino", "en_progreso", "completado"]


class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    email: str
    role: str  # customer | washer | admin
    phone: Optional[str] = None
    zone: Optional[str] = None
    rating: Optional[float] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class Service(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str
    duration_minutes: int
    base_price: int  # ARS for car (base multiplier 1.0)
    badge: Optional[str] = None
    features: List[str] = []
    active: bool = True


class Booking(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    customer_id: str
    customer_name: str
    washer_id: Optional[str] = None
    washer_name: Optional[str] = None
    service_id: str
    service_name: str
    vehicle_type: str  # car | suv | large
    vehicle_label: str
    address: str
    zone: str
    date: str  # YYYY-MM-DD
    time: str  # HH:mm
    price: int
    status: str = "pendiente"
    notes: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class BookingCreate(BaseModel):
    customer_id: str
    service_id: str
    vehicle_type: str
    address: str
    zone: str
    date: str
    time: str
    notes: Optional[str] = None


class StatusUpdate(BaseModel):
    status: str


class AssignWasher(BaseModel):
    washer_id: str


class ServiceCreate(BaseModel):
    name: str
    description: str
    duration_minutes: int
    base_price: int
    badge: Optional[str] = None
    features: List[str] = []


class ServiceUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    duration_minutes: Optional[int] = None
    base_price: Optional[int] = None
    badge: Optional[str] = None
    features: Optional[List[str]] = None
    active: Optional[bool] = None


class UserCreate(BaseModel):
    name: str
    email: str
    role: str
    phone: Optional[str] = None
    zone: Optional[str] = None


# ---------- Helpers ----------
def clean(doc: Dict[str, Any]) -> Dict[str, Any]:
    if doc is None:
        return None
    doc.pop("_id", None)
    return doc


def calc_price(service_price: int, vehicle_type: str) -> int:
    mult = VEHICLE_TYPES.get(vehicle_type, {}).get("multiplier", 1.0)
    return int(round(service_price * mult / 100.0) * 100)


# ---------- Seed data ----------
async def seed_data():
    users_count = await db.users.count_documents({})
    if users_count == 0:
        demo_users = [
            # customers
            {"id": "cust-1", "name": "Martina Álvarez", "email": "martina@demo.ar", "role": "customer", "phone": "+54 11 5555-1101", "zone": "CABA - Palermo", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "cust-2", "name": "Nicolás Fernández", "email": "nico@demo.ar", "role": "customer", "phone": "+54 11 5555-1102", "zone": "GBA Norte - San Isidro", "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "cust-3", "name": "Camila Rodríguez", "email": "cami@demo.ar", "role": "customer", "phone": "+54 11 5555-1103", "zone": "CABA - Belgrano", "created_at": datetime.now(timezone.utc).isoformat()},
            # washers
            {"id": "wash-1", "name": "Diego Ramírez", "email": "diego@demo.ar", "role": "washer", "phone": "+54 11 6666-2201", "zone": "CABA", "rating": 4.9, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "wash-2", "name": "Lucas Pereyra", "email": "lucas@demo.ar", "role": "washer", "phone": "+54 11 6666-2202", "zone": "GBA Norte", "rating": 4.95, "created_at": datetime.now(timezone.utc).isoformat()},
            {"id": "wash-3", "name": "Sofía Torres", "email": "sofia@demo.ar", "role": "washer", "phone": "+54 11 6666-2203", "zone": "GBA Oeste", "rating": 4.8, "created_at": datetime.now(timezone.utc).isoformat()},
            # admin
            {"id": "admin-1", "name": "Administración LAVADOSYA!", "email": "admin@demo.ar", "role": "admin", "phone": "+54 11 7777-3300", "created_at": datetime.now(timezone.utc).isoformat()},
        ]
        await db.users.insert_many(demo_users)
        logger.info("Seeded demo users.")

    services_count = await db.services.count_documents({})
    if services_count == 0:
        demo_services = [
            {
                "id": "svc-basico",
                "name": "Lavado Básico Eco",
                "description": "Lavado exterior rápido y eficiente para el día a día.",
                "duration_minutes": 35,
                "base_price": 8000,
                "badge": "Rápido",
                "features": ["Lavado exterior con hidrolavadora", "Limpieza de cristales", "Secado con microfibra", "Acondicionador de neumáticos"],
                "active": True,
            },
            {
                "id": "svc-completo",
                "name": "Lavado Completo Premium",
                "description": "Exterior e interior, perfecto para mantener tu auto impecable.",
                "duration_minutes": 60,
                "base_price": 14500,
                "badge": "Recomendado",
                "features": ["Exterior completo + cera", "Aspirado profundo", "Limpieza de torpedo y consola", "Perfume de autor"],
                "active": True,
            },
            {
                "id": "svc-premium",
                "name": "Lavado Premium Hydro",
                "description": "Tratamiento acrílico, higienización y detallado exterior profundo.",
                "duration_minutes": 90,
                "base_price": 22000,
                "badge": "Alta Gama",
                "features": ["Acrílico rápido exterior", "Higienización de baúl", "Desinfección con aire a presión", "Llantas y pasarruedas"],
                "active": True,
            },
            {
                "id": "svc-detailing",
                "name": "Detailing Interior Profundo",
                "description": "Restauración interior nivel profesional: tapizados, cuero y aire.",
                "duration_minutes": 140,
                "base_price": 35000,
                "badge": "Máximo Nivel",
                "features": ["Inyección y extracción de manchas", "Nutrición de cueros", "Ozono purificador de aire", "Descontaminado cerámico"],
                "active": True,
            },
        ]
        await db.services.insert_many(demo_services)
        logger.info("Seeded demo services.")

    bookings_count = await db.bookings.count_documents({})
    if bookings_count == 0:
        now = datetime.now(timezone.utc).isoformat()
        demo_bookings = [
            {
                "id": "bk-1", "customer_id": "cust-1", "customer_name": "Martina Álvarez",
                "washer_id": "wash-1", "washer_name": "Diego Ramírez",
                "service_id": "svc-completo", "service_name": "Lavado Completo Premium",
                "vehicle_type": "car", "vehicle_label": "Auto chico / Sedán",
                "address": "Av. del Libertador 2450, Palermo", "zone": "CABA - Palermo",
                "date": "2026-02-20", "time": "11:00", "price": 14500,
                "status": "en_camino", "notes": "Portón negro, timbre B", "created_at": now, "updated_at": now,
            },
            {
                "id": "bk-2", "customer_id": "cust-2", "customer_name": "Nicolás Fernández",
                "washer_id": None, "washer_name": None,
                "service_id": "svc-premium", "service_name": "Lavado Premium Hydro",
                "vehicle_type": "suv", "vehicle_label": "Pickup mediana / SUV",
                "address": "Belgrano 123, San Isidro", "zone": "GBA Norte - San Isidro",
                "date": "2026-02-21", "time": "14:00", "price": 29700,
                "status": "pendiente", "notes": None, "created_at": now, "updated_at": now,
            },
            {
                "id": "bk-3", "customer_id": "cust-3", "customer_name": "Camila Rodríguez",
                "washer_id": "wash-2", "washer_name": "Lucas Pereyra",
                "service_id": "svc-basico", "service_name": "Lavado Básico Eco",
                "vehicle_type": "car", "vehicle_label": "Auto chico / Sedán",
                "address": "Juramento 1890, Belgrano", "zone": "CABA - Belgrano",
                "date": "2026-02-18", "time": "09:00", "price": 8000,
                "status": "completado", "notes": None, "created_at": now, "updated_at": now,
            },
            {
                "id": "bk-4", "customer_id": "cust-1", "customer_name": "Martina Álvarez",
                "washer_id": "wash-3", "washer_name": "Sofía Torres",
                "service_id": "svc-detailing", "service_name": "Detailing Interior Profundo",
                "vehicle_type": "large", "vehicle_label": "Vehículo grande / Van",
                "address": "Rivadavia 5500, Caballito", "zone": "CABA - Caballito",
                "date": "2026-02-15", "time": "16:30", "price": 59500,
                "status": "completado", "notes": None, "created_at": now, "updated_at": now,
            },
            {
                "id": "bk-5", "customer_id": "cust-2", "customer_name": "Nicolás Fernández",
                "washer_id": None, "washer_name": None,
                "service_id": "svc-completo", "service_name": "Lavado Completo Premium",
                "vehicle_type": "suv", "vehicle_label": "Pickup mediana / SUV",
                "address": "Av. Maipú 1100, Vicente López", "zone": "GBA Norte - Vicente López",
                "date": "2026-02-22", "time": "18:00", "price": 19600,
                "status": "pendiente", "notes": "Preferentemente con cera extra", "created_at": now, "updated_at": now,
            },
        ]
        await db.bookings.insert_many(demo_bookings)
        logger.info("Seeded demo bookings.")


@app.on_event("startup")
async def on_startup():
    await seed_data()


@app.on_event("shutdown")
async def on_shutdown():
    client.close()


# ---------- Routes ----------
@api_router.get("/")
async def root():
    return {"app": "LAVADOSYA!", "status": "ok", "version": "0.1.0"}


@api_router.get("/vehicle-types")
async def get_vehicle_types():
    return list(VEHICLE_TYPES.values())


@api_router.get("/zones")
async def get_zones():
    return [
        "CABA - Palermo", "CABA - Belgrano", "CABA - Recoleta",
        "CABA - Puerto Madero", "CABA - Caballito", "CABA - San Telmo",
        "GBA Norte - San Isidro", "GBA Norte - Vicente López", "GBA Norte - Tigre",
        "GBA Oeste - Ramos Mejía", "GBA Oeste - Morón",
        "GBA Sur - Quilmes", "GBA Sur - Lanús",
    ]


# Users
@api_router.get("/users")
async def list_users(role: Optional[str] = None):
    q = {"role": role} if role else {}
    docs = await db.users.find(q, {"_id": 0}).to_list(1000)
    return docs


@api_router.get("/users/{user_id}")
async def get_user(user_id: str):
    doc = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Usuario no encontrado")
    return doc


@api_router.post("/users")
async def create_user(payload: UserCreate):
    user = User(**payload.model_dump())
    await db.users.insert_one(user.model_dump())
    return user.model_dump()


@api_router.delete("/users/{user_id}")
async def delete_user(user_id: str):
    res = await db.users.delete_one({"id": user_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Usuario no encontrado")
    return {"ok": True}


# Services
@api_router.get("/services")
async def list_services():
    docs = await db.services.find({}, {"_id": 0}).to_list(1000)
    return docs


@api_router.post("/services")
async def create_service(payload: ServiceCreate):
    svc = Service(**payload.model_dump())
    await db.services.insert_one(svc.model_dump())
    return svc.model_dump()


@api_router.patch("/services/{service_id}")
async def update_service(service_id: str, payload: ServiceUpdate):
    update = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not update:
        raise HTTPException(400, "Nada para actualizar")
    res = await db.services.update_one({"id": service_id}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(404, "Servicio no encontrado")
    doc = await db.services.find_one({"id": service_id}, {"_id": 0})
    return doc


@api_router.delete("/services/{service_id}")
async def delete_service(service_id: str):
    res = await db.services.delete_one({"id": service_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Servicio no encontrado")
    return {"ok": True}


# Bookings
@api_router.get("/bookings")
async def list_bookings(
    customer_id: Optional[str] = None,
    washer_id: Optional[str] = None,
    status: Optional[str] = None,
    unassigned: Optional[bool] = None,
):
    q: Dict[str, Any] = {}
    if customer_id:
        q["customer_id"] = customer_id
    if washer_id:
        q["washer_id"] = washer_id
    if status:
        q["status"] = status
    if unassigned:
        q["washer_id"] = None
    docs = await db.bookings.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return docs


@api_router.post("/bookings")
async def create_booking(payload: BookingCreate):
    if payload.vehicle_type not in VEHICLE_TYPES:
        raise HTTPException(400, "Tipo de vehículo inválido")
    service = await db.services.find_one({"id": payload.service_id}, {"_id": 0})
    if not service:
        raise HTTPException(400, "Servicio inválido")
    customer = await db.users.find_one({"id": payload.customer_id, "role": "customer"}, {"_id": 0})
    if not customer:
        raise HTTPException(400, "Cliente inválido")

    price = calc_price(service["base_price"], payload.vehicle_type)
    booking = Booking(
        customer_id=customer["id"],
        customer_name=customer["name"],
        service_id=service["id"],
        service_name=service["name"],
        vehicle_type=payload.vehicle_type,
        vehicle_label=VEHICLE_TYPES[payload.vehicle_type]["label"],
        address=payload.address,
        zone=payload.zone,
        date=payload.date,
        time=payload.time,
        price=price,
        notes=payload.notes,
        status="pendiente",
    )
    await db.bookings.insert_one(booking.model_dump())
    return booking.model_dump()


@api_router.get("/bookings/{booking_id}")
async def get_booking(booking_id: str):
    doc = await db.bookings.find_one({"id": booking_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Reserva no encontrada")
    return doc


@api_router.patch("/bookings/{booking_id}/status")
async def update_status(booking_id: str, payload: StatusUpdate):
    if payload.status not in STATUS_FLOW + ["cancelado"]:
        raise HTTPException(400, "Estado inválido")
    res = await db.bookings.update_one(
        {"id": booking_id},
        {"$set": {"status": payload.status, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Reserva no encontrada")
    return await db.bookings.find_one({"id": booking_id}, {"_id": 0})


@api_router.patch("/bookings/{booking_id}/assign")
async def assign_washer(booking_id: str, payload: AssignWasher):
    washer = await db.users.find_one({"id": payload.washer_id, "role": "washer"}, {"_id": 0})
    if not washer:
        raise HTTPException(400, "Lavador inválido")
    res = await db.bookings.update_one(
        {"id": booking_id},
        {
            "$set": {
                "washer_id": washer["id"],
                "washer_name": washer["name"],
                "status": "aceptado",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Reserva no encontrada")
    return await db.bookings.find_one({"id": booking_id}, {"_id": 0})


@api_router.patch("/bookings/{booking_id}/accept")
async def accept_booking(booking_id: str, payload: AssignWasher):
    """Washer self-accepts a booking from the pool."""
    return await assign_washer(booking_id, payload)


@api_router.patch("/bookings/{booking_id}/reject")
async def reject_booking(booking_id: str):
    """Washer rejects — booking stays unassigned, available to others."""
    doc = await db.bookings.find_one({"id": booking_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Reserva no encontrada")
    return doc


@api_router.delete("/bookings/{booking_id}")
async def delete_booking(booking_id: str):
    res = await db.bookings.delete_one({"id": booking_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Reserva no encontrada")
    return {"ok": True}


# Price estimator
@api_router.get("/estimate")
async def estimate(service_id: str, vehicle_type: str):
    svc = await db.services.find_one({"id": service_id}, {"_id": 0})
    if not svc:
        raise HTTPException(404, "Servicio no encontrado")
    if vehicle_type not in VEHICLE_TYPES:
        raise HTTPException(400, "Tipo de vehículo inválido")
    return {
        "service_id": service_id,
        "vehicle_type": vehicle_type,
        "price": calc_price(svc["base_price"], vehicle_type),
    }


# Admin stats
@api_router.get("/stats")
async def admin_stats():
    bookings = await db.bookings.find({}, {"_id": 0}).to_list(5000)
    washers = await db.users.count_documents({"role": "washer"})
    customers = await db.users.count_documents({"role": "customer"})
    completed = [b for b in bookings if b["status"] == "completado"]
    revenue = sum(b["price"] for b in completed)
    active = [b for b in bookings if b["status"] in ("aceptado", "en_camino", "en_progreso")]
    pending = [b for b in bookings if b["status"] == "pendiente"]

    # revenue by service
    by_service: Dict[str, int] = {}
    for b in completed:
        by_service[b["service_name"]] = by_service.get(b["service_name"], 0) + b["price"]

    # bookings by status
    by_status: Dict[str, int] = {}
    for b in bookings:
        by_status[b["status"]] = by_status.get(b["status"], 0) + 1

    return {
        "revenue_total": revenue,
        "bookings_total": len(bookings),
        "bookings_completed": len(completed),
        "bookings_active": len(active),
        "bookings_pending": len(pending),
        "washers_total": washers,
        "customers_total": customers,
        "revenue_by_service": [{"name": k, "value": v} for k, v in by_service.items()],
        "bookings_by_status": [{"status": k, "value": v} for k, v in by_status.items()],
    }


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
