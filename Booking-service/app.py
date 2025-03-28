from flask import Flask, request, jsonify
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from models import Booking, Base
import os
from dotenv import load_dotenv
import logging
import requests

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)

# Database configuration
DATABASE_URL = os.getenv("BOOKING_DB_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

NOTIFICATION_SERVICE_URL = "http://notification-service:5004/send-email"

def notify_user(booking_id, user_email):
    """Send booking confirmation request to the Notification Service"""
    try:
        payload = {
            "booking_id": booking_id,
            "user_email": user_email
        }
        response = requests.post(f"{NOTIFICATION_SERVICE_URL}", json=payload)

        if response.status_code == 200:
            logging.info(f"✅ Notification sent successfully: {payload}")
        else:
            logging.error(f"❌ Failed to send notification: {response.text}")

    except Exception as e:
        logging.error(f"❌ Error calling Notification Service: {str(e)}")

@app.route('/bookings', methods=['POST'])
def create_booking():
    """Create a new booking and publish confirmation event"""
    data = request.get_json()
    logging.debug(f"Incoming request data: {data}")

    # Validate required fields
    required_fields = ["user_id", "event_id", "tickets", "amount", "user_email"]
    for field in required_fields:
        if field not in data:
            logging.error(f"Missing required field: {field}")
            return jsonify({"error": f"Missing required field: {field}"}), 400

    db = SessionLocal()
    try:
        # Create booking record
        booking = Booking(
            user_id=data["user_id"],
            event_id=data["event_id"],
            tickets=data["tickets"],
            amount=data["amount"],
            status="confirmed"
        )
        
        db.add(booking)
        db.commit()
        db.refresh(booking)
        logging.info(f"Booking created: ID {booking.id}")

        # Publish confirmation event
        notify_user(
            booking_id=booking.id,
            user_email=data["user_email"]
        )

        return jsonify({
            "id": booking.id,
            "user_id": booking.user_id,
            "event_id": booking.event_id,
            "tickets": booking.tickets,
            "amount": booking.amount,
            "status": booking.status
        }), 201

    except Exception as e:
        db.rollback()
        logging.error(f"Booking creation failed: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

    finally:
        db.close()

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5003)