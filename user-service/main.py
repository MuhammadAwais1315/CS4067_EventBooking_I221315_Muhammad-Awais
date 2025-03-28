from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from database import SessionLocal, engine
from models import User
from auth import get_password_hash, verify_password, create_access_token
import logging
from database import SessionLocal, engine, Base 
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List
import httpx
from fastapi import HTTPException, status

# Add configuration
EVENT_SERVICE_URL = "http://event-service:5000/events" 
BOOKING_SERVICE_URL = "http://booking-service:5003/bookings"

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(level=logging.INFO)

# ========== Pydantic Models ==========
class UserRegister(BaseModel):
    email: str
    password: str
    name: str

class UserLogin(BaseModel):
   
    # Change from 'email' to 'username'
    username: str  # Previously: email: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    user_id: int



# Initialize database
Base.metadata.create_all(bind=engine)

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Registration endpoint - Updated to use Pydantic model
@app.post("/register", response_model=dict)
async def register_user(user: UserRegister, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == user.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered"
        )
    
    hashed_password = get_password_hash(user.password)
    new_user = User(
        email=user.email,
        password_hash=hashed_password,
        name=user.name
    )
    
    db.add(new_user)
    db.commit()
    logging.info(f"New user registered: {user.email}")
    return {"message": "User registered successfully"}

# Login endpoint - Updated to use Pydantic model
@app.post("/login", response_model=Token)
async def login(user: UserLogin, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.email == user.username).first()
    
    if not db_user or not verify_password(user.password, db_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(data={"sub": db_user.email})
    logging.info(f"User Login: {db_user.email}")
    print(db_user.id)
    response_data = {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": db_user.id  # Ensure this is an integer
    }

    print(f"Login Response: {response_data}")  # 🔍 Debugging log
    return response_data

# Profile management endpoint
@app.get("/users/{user_id}", response_model=dict)
async def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name
    }

# Add to imports

# Define fetch_event function
async def fetch_event(event_id: str):
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{EVENT_SERVICE_URL}/{event_id}")
        return response.json() if response.status_code == 200 else None 

async def edit_event(event_id: str, data: dict):
    async with httpx.AsyncClient() as client:
        response = await client.put(f"{EVENT_SERVICE_URL}/{event_id}/edit", json=data)
        return response.json() if response.status_code == 200 else None

from fastapi import HTTPException, status

# Add Pydantic model for booking creation
class BookingCreate(BaseModel):
    user_id: int
    event_id: str
    tickets: int

# Modify booking creation request to include user_email
@app.post("/bookings", response_model=dict)
async def create_booking(
    booking: BookingCreate,  # Your existing Pydantic model
    db: Session = Depends(get_db)
):
    # Fetch user details (including email) from the User Service database
    user = db.query(User).filter(User.id == booking.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Calculate amount using Event Service
    event = await fetch_event(booking.event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found") 
    amount = booking.tickets * event["price"]

    # Call Booking Service with user_email
    booking_data = {
        "user_id": booking.user_id,
        "event_id": booking.event_id,
        "tickets": booking.tickets,
        "amount": amount,
        "user_email": user.email  # ✅ Critical addition
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(BOOKING_SERVICE_URL, json=booking_data, timeout=30.0)
        # if response is ok mean booking confirmed then edit the event tickets
        if response.status_code == 201:
            # Update event tickets
            new_tickets_available = event["tickets_available"] - booking.tickets
            edit_data = {
                         "name": event["name"],
                         "location": event["location"],
                            "date": event["date"],
                            "price": event["price"],
                            "tickets_available": new_tickets_available,
                            "description": event["description"],
                            "picture": event["picture"]
                        }
            await edit_event(booking.event_id, edit_data)
    return response.json()

# ... (previous imports)
from bson import ObjectId  # Add this import

# ========== Updated Pydantic Models ==========
class EventResponse(BaseModel):
    id: str = Field(..., alias= "_id" )
    name: str
    location: str
    date: str  # Now matches raw date string from MongoDB
    price: float
    tickets_available: int
    description: str
    picture: str
    class Config:
        populate_by_name = True

   

# ========== Updated Endpoint ==========
@app.get("/events", response_model=List[EventResponse])
async def get_events(
    search: Optional[str] = None,
    page: int = 1,
    db: Session = Depends(get_db)
):
    try:
        async with httpx.AsyncClient() as client:
            params = {"search": search, "page": page}
            response = await client.get(EVENT_SERVICE_URL, params=params)
            response.raise_for_status()
            
            data = response.json()
            # Explicitly validate each event
            return [EventResponse(**event) for event in data['events']]
            
    except httpx.HTTPError as e:
        logging.error(f"Event service error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Event service unavailable"
        )

class Event(BaseModel):
    name: str
    location: str = ""
    date: str = ""
    price: float = 0.0
    tickets_available: int = 0
    description: str = ""
    picture: str = "https://via.placeholder.com/400x250"

@app.post("/create")
async def create(event: Event):
    url = f"{EVENT_SERVICE_URL}/create"  # Update this if Flask runs on a different host/port
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=event.model_dump())
        return {
            "status_code": response.status_code,
            "response": response.json()
        }