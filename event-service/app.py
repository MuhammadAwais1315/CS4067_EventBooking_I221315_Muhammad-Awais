from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from pymongo import MongoClient
from bson.objectid import ObjectId
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')

client = MongoClient(os.getenv('MONGO_URI'))
db = client['event_db']
events_collection = db['events']

# Helper function to format date
def format_date(date_str):
    return datetime.strptime(date_str, '%Y-%m-%d').strftime('%B %d, %Y')

@app.route('/')
def index():
    search_query = request.args.get('search', '')
    page = int(request.args.get('page', 1))
    per_page = 6
    
    query = {}
    if search_query:
        query['$or'] = [
            {'name': {'$regex': search_query, '$options': 'i'}},
            {'location': {'$regex': search_query, '$options': 'i'}},
            {'description': {'$regex': search_query, '$options': 'i'}}
        ]
    
    total_events = events_collection.count_documents(query)
    events = list(events_collection.find(query).skip((page-1)*per_page).limit(per_page))
    
    return render_template('index.html',
                         events=events,
                         search_query=search_query,
                         page=page,
                         total_pages=(total_events // per_page) + 1,
                         format_date=format_date)

@app.route('/events/create', methods=['POST'])
def create_event():
    try:
        if request.is_json:  # If the request is JSON
            event_data = request.get_json()
        else:  # If the request is form-data
            event_data = request.form.to_dict()

        name = event_data.get('name')
        if not name:
            return jsonify({"error": "Missing 'name' field"}), 400

        event = {
            'name': name,
            'location': event_data.get('location', ''),
            'date': event_data.get('date', ''),
            'price': float(event_data.get('price', 0)),
            'tickets_available': int(event_data.get('tickets_available', 0)),
            'description': event_data.get('description', ''),
            'picture': event_data.get('picture', 'https://via.placeholder.com/400x250')
        }

        result = events_collection.insert_one(event)
        return jsonify({"message": "Event created successfully!", "event_id": str(result.inserted_id)}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500


from flask import jsonify

@app.route('/events/<event_id>')
def event_detail(event_id):
    event = events_collection.find_one({'_id': ObjectId(event_id)})
    if not event:
        return jsonify({'error': 'Event not found!'}), 404
    
    # Convert ObjectId to string for JSON compatibility
    event['_id'] = str(event['_id'])
    
    return jsonify(event)

@app.route('/api/events/<event_id>/edit', methods=['PUT'])
def edit_event(event_id):
    event = events_collection.find_one({'_id': ObjectId(event_id)})
    if not event:
        flash('Event not found!', 'danger')
        return redirect(url_for('index'))
    
    if request.method == 'PUT':
        try:
            if request.is_json:  # Handle JSON request
                update_data = request.get_json()
            else:  # Handle form-data request
                update_data = request.form.to_dict()

            # Validate required fields
            name = update_data.get('name')
            if not name:
                return jsonify({"error": "Missing 'name' field"}), 400

            update_data['price'] = float(update_data.get('price', 0))
            update_data['tickets_available'] = int(update_data.get('tickets_available', 0))

            events_collection.update_one({'_id': ObjectId(event_id)}, {'$set': update_data})
            flash('Event updated successfully!', 'success')
            return jsonify({"message": "Event updated successfully"}), 200

        except Exception as e:
            return jsonify({"error": str(e)}), 500

    return render_template('edit_event.html', event=event)


@app.route('/events/<event_id>/delete', methods=['POST'])
def delete_event(event_id):
    events_collection.delete_one({'_id': ObjectId(event_id)})
    if 'my_events' in session and event_id in session['my_events']:
        session['my_events'].remove(event_id)
    flash('Event deleted successfully!', 'success')
    return redirect(url_for('index'))

@app.route('/my-events')
def my_events():
    if 'my_events' not in session or not session['my_events']:
        flash('You haven\'t created any events yet!', 'info')
        return redirect(url_for('index'))
    
    event_ids = [ObjectId(eid) for eid in session['my_events']]
    events = list(events_collection.find({'_id': {'$in': event_ids}}))
    return render_template('my_events.html', events=events, format_date=format_date)

@app.route('/add-to-cart/<event_id>')
def add_to_cart(event_id):
    if 'cart' not in session:
        session['cart'] = []
    
    if event_id not in session['cart']:
        session['cart'].append(event_id)
        session.modified = True
        flash('Event added to cart!', 'success')
    else:
        flash('Event already in cart!', 'info')
    return redirect(request.referrer)

@app.route('/cart')
def view_cart():
    if 'cart' not in session or not session['cart']:
        flash('Your cart is empty!', 'info')
        return redirect(url_for('index'))
    
    event_ids = [ObjectId(eid) for eid in session['cart']]
    events = list(events_collection.find({'_id': {'$in': event_ids}}))
    return render_template('cart.html', events=events, format_date=format_date)

@app.route('/remove-from-cart/<event_id>')
def remove_from_cart(event_id):
    if 'cart' in session and event_id in session['cart']:
        session['cart'].remove(event_id)
        session.modified = True
        flash('Event removed from cart!', 'success')
    return redirect(url_for('view_cart'))
# ... (previous imports remain the same)

@app.route('/api/events')
def api_events():
    search_query = request.args.get('search', '')
    page = int(request.args.get('page', 1))
    per_page = 6

    query = {}
    if search_query:
        query['$or'] = [
            {'name': {'$regex': search_query, '$options': 'i'}},
            {'location': {'$regex': search_query, '$options': 'i'}},
            {'description': {'$regex': search_query, '$options': 'i'}}
        ]
    
    events = list(events_collection.find(query).skip((page-1)*per_page).limit(per_page))
    
    # Convert MongoDB objects to JSON format
    for event in events:
        event['_id'] = str(event['_id'])  # Convert ObjectId to string
        # Keep date in raw format (YYYY-MM-DD)
        # Remove format_date() call
    
    return {
        'page': page,
        'total_pages': (events_collection.count_documents(query) // per_page) + 1,
        'events': events
    }
from bson import ObjectId

from bson import ObjectId

@app.route('/api/events/<event_id>')
def api_event(event_id):
    try:
        # Convert string to MongoDB ObjectId
        event = events_collection.find_one({'_id': ObjectId(event_id)})
        if not event:
            return jsonify({"error": "Event not found"}), 404
        
        # Convert MongoDB data to JSON
        event['_id'] = str(event['_id'])
        return jsonify(event)
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)