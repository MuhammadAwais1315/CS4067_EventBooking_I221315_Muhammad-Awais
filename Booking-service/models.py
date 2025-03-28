from sqlalchemy import Column, Integer, Float, String, DateTime, func  # Add func import
from database import Base
from datetime import datetime

class Booking(Base):
    __tablename__ = "bookings"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer)
    event_id = Column(String)  # Changed from Integer to String
    tickets = Column(Integer)
    amount = Column(Float)
    status = Column(String, default="pending")
    created_at = Column(DateTime, server_default=func.now())

    created_at = Column(DateTime, server_default=func.now())  # Use server_default

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "event_id": self.event_id,
            "tickets": self.tickets,
            "amount": self.amount,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }