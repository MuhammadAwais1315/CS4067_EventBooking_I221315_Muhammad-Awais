import pika
import json
from flask import Flask, request, jsonify
from flask_mail import Mail, Message
from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Configure Flask-Mail for email notifications
app.config['MAIL_SERVER'] = os.getenv("MAIL_SERVER")
app.config['MAIL_PORT'] = int(os.getenv("MAIL_PORT"))
app.config['MAIL_USERNAME'] = os.getenv("MAIL_USERNAME")
app.config['MAIL_PASSWORD'] = os.getenv("MAIL_PASSWORD")
app.config['MAIL_USE_TLS'] = True
mail = Mail(app)


def get_mongo_client():
    mongo_url = os.getenv("MONGO_URL")
    mongo_port = int(os.getenv("MONGO_PORT"))
    return MongoClient(host=mongo_url, port=mongo_port)

# MongoDB setup
mongo_client = get_mongo_client()
db = mongo_client[os.getenv("MONGO_DB")]
notifications_collection = db.notifications



def send_confirmation_email(booking_data):
    """Send email using Flask-Mail with proper app context"""
    with app.app_context():
        try:
            msg = Message(
                subject="Booking Confirmation",
                sender=os.getenv("MAIL_USERNAME"),
                recipients=[booking_data["user_email"]],
                body=f"Dear User,\n\nYour booking {booking_data['booking_id']} is confirmed!\n\nBest Regards,\nYour Company"
            )
            mail.send(msg)
            
            # Log notification in MongoDB
            notifications_collection.insert_one({
                "booking_id": booking_data["booking_id"],
                "user_email": booking_data["user_email"],
                "status": "sent",
                "message": "Confirmation email sent successfully"
            })
            return {"success": True, "message": "Email sent successfully"}
        except Exception as e:
            notifications_collection.insert_one({
                "status": "failed",
                "error": str(e)
            })
            return {"success": False, "message": str(e)}

@app.route("/send-email", methods=["POST"])
def send_email_api():
    """API to trigger email notification manually"""
    try:
        data = request.get_json()
        if not data or "booking_id" not in data or "user_email" not in data:
            return jsonify({"error": "Invalid request data"}), 400
        
        response = send_confirmation_email(data)
        return jsonify(response)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/test", methods=["GET"])
def test():
    return jsonify({"message": "API is running"})

def consume_booking_events():
    """RabbitMQ Consumer for booking confirmations"""
    try:
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                host=os.getenv("RABBITMQ_HOST"),
                port=int(os.getenv("RABBITMQ_PORT"))
            )
        )
        channel = connection.channel()
        
        channel.queue_declare(queue='booking_confirmed')
        
        def callback(ch, method, properties, body):
            booking_data = json.loads(body)
            print(f"📩 Received booking confirmation: {booking_data}")
            send_confirmation_email(booking_data)
        
        channel.basic_consume(
            queue='booking_confirmed',
            on_message_callback=callback,
            auto_ack=True
        )
        
        print("🚀 Waiting for booking confirmations...")
        channel.start_consuming()
    
    except Exception as e:
        print(f"❌ RabbitMQ connection error: {str(e)}")

if __name__ == "__main__":
    # Start RabbitMQ consumer in a separate thread
    import threading
    threading.Thread(target=consume_booking_events, daemon=True).start()
    
    # Start Flask app
    app.run(host="0.0.0.0", port=5004)
