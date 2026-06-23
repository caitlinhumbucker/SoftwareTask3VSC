from flask import Flask, render_template, request, redirect, url_for, flash, session, make_response, send_from_directory
import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime

# Initialise the Flask application
app = Flask(__name__)
app.secret_key='your-secret-key-here'

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config[ 'UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure upload directory exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
# Check uploaded file is an allowed extension.
def allowed_file(filename) :
    return ''in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_db():
    db = sqlite3.connect('database/photo_journal.db')
    db.row_factory = sqlite3.Row
    return db

# Define the route for the homepage
@app.route('/')
def index():
    # Check if the user is logged in by verifying the session
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # Get the search term and sort option from the URL
    search_query = request.args.get('search', '')
    current_sort = request.args.get('sort', 'newest')

    # Only allow specific sort options to prevent SQL injection
    allowed_sorts = {
        'newest': 'created_at DESC',
        'oldest': 'created_at ASC',
        'expiry_soon': 'expiry_date ASC',
        'expiry_far': 'expiry_date DESC'
    }
    order_by = allowed_sorts.get(current_sort, 'created_at DESC')

    db = get_db()
    entries = db.execute(f'''
        SELECT * FROM entries
        WHERE user_id = ? AND title LIKE ?
        ORDER BY {order_by}
    ''', (session['user_id'], f"%{search_query}%")).fetchall()

    return render_template('index.html', entries=entries, search_query=search_query, current_sort=current_sort)
           

# Define the route for login functionality, supporting GET and POST methods
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method=='POST':
        username= request.form['username']
        password=request.form['password']
        db=get_db()
        user=db.execute(
            'SELECT * FROM users WHERE username = ?', (username,)
        ).fetchone()

        if user and check_password_hash(user['password'], password):
            session. clear ()
            session[ 'user_id'] = user['id']
            session[ 'username'] = user[ 'username']
            return redirect(url_for('index'))
        flash('Invalid username or password', 'error')
            
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        db = get_db()
        try:
            db.execute(
                'INSERT INTO users (username, password) VALUES (?, ?)',
                (username, generate_password_hash(password))
            )
            db.commit()
            flash('Registration suessful! Please log in.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash("Username already exists!", "error")
            
    return render_template('register.html')

# Clears session when user attempts to log out
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/building') # Route for reciple building page, NOT FULLY COMPLETED
def building():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    return render_template('building.html')

@app.route('/add_entry', methods=['POST'])
def add_entry():
    if 'user_id' not in session: # Ensures that users cannot make an entry when logged out
        return redirect(url_for('login'))
    
    if 'image' not in request.files: # Ensures the users uploads a photo when creating an entry
        flash('No image uploaded', 'error')
        return redirect(url_for('index'))
    
    file = request.files['image']
    if file.filename == '':
        flash('No image selected', 'error')
        return redirect(url_for('index'))
    
    if file and allowed_file(file.filename):
        filename = secure_filename(f"{datetime.now().timestamp()}_{file.filename}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        db = get_db()
        db.execute('''
            INSERT INTO entries (
                user_id, title, description, image_path,
                quantity, expiry_date, calories, protein,
                sugar, sodium, saturated_fat
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            session['user_id'],
            request.form['title'],
            request.form['description'],
            f"uploads/{filename}",
            request.form.get('quantity'),
            request.form.get('expiry_date'),
            request.form.get('calories'),
            request.form.get('protein'),
            request.form.get('sugar'),
            request.form.get('sodium'),
            request.form.get('saturated_fat')
        ))
        db.commit()
        flash('Entry added successfully!', 'success')
        return redirect(url_for('index'))
    
    else:
        flash('Invalid file type', 'error')
        return redirect(url_for('index'))
#Returns a response once recognises user is offline
@app.route('/offline')
def offline():
    response = make_response(render_template('offline.html'))
    return response

# Define the route for the service worker
@app.route('/service-worker.js')
def sw():
    response = make_response(
        send_from_directory(os.path.join(app.root_path, 'static/js'), 'service-worker.js')
    )
    return response

# Define the route for the manifest.json file
@app.route('/manifest.json')
def manifest():
    return send_from_directory(os.path.join(app.root_path, 'static'), 'manifest.json')

@app.route('/edit_entry/<int:entry_id>', methods=['POST'])
def edit_entry(entry_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    db = get_db()
    entry = db.execute(
        'SELECT * FROM entries WHERE id = ? AND user_id = ?',
        (entry_id, session['user_id'])
    ).fetchone()

    if not entry:
        flash('Entry not found or access denied', 'error')
        return redirect(url_for('index'))

    title = request.form['title']
    description = request.form['description']

    # If new image uploaded
    if 'image' in request.files and request.files['image'].filename != '':
        file = request.files['image']

        if allowed_file(file.filename):
            try:
                old_image_path = os.path.join(app.root_path, 'static', entry['image_path'])
                if os.path.exists(old_image_path):
                    os.remove(old_image_path)
            except Exception as e:
                print(f"Error deleting old image: {e}")

            filename = secure_filename(f"{datetime.now().timestamp()}_{file.filename}")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            db.execute('''
                UPDATE entries
                SET title = ?, description = ?, image_path = ?
                WHERE id = ? AND user_id = ?
            ''', (title, description, f"uploads/{filename}", entry_id, session['user_id']))

        else:
            flash('Invalid file type', 'error')
            return redirect(url_for('index'))

    # No new image → update only text
    else:
        db.execute('''
            UPDATE entries
            SET title = ?, description = ?
            WHERE id = ? AND user_id = ?
        ''', (title, description, entry_id, session['user_id']))

    db.commit()
    flash('Entry updated successfully!', 'success')
    return redirect(url_for('index'))

# Route to delete a specific ingredient entry
@app.route('/delete_entry/<int:entry_id>', methods=['POST'])
def delete_entry(entry_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    db = get_db()
    # Fetch the entry, make sure it belongs to the logged in user
    entry = db.execute(
        'SELECT * FROM entries WHERE id = ? AND user_id = ?',
        (entry_id, session['user_id'])
    ).fetchone()

    if not entry:
        flash('Entry not found or access denied', 'error')
        return redirect(url_for('index'))

    # Attempt to delete image
    try:
        image_path = os.path.join(app.root_path, 'static', entry['image_path'])
        if os.path.exists(image_path):
            os.remove(image_path)
    except Exception as e:
        print(f"Error deleting image file: {e}")

    # Delete database entry
    db.execute(
        'DELETE FROM entries WHERE id = ? AND user_id = ?',
        (entry_id, session['user_id'])
    )
    db.commit()

    flash('Entry deleted successfully!', 'success')
    return redirect(url_for('index'))

# Route to display the full details of a singular ingredient
@app.route('/entry/<int:entry_id>')
def entry_detail(entry_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    db = get_db()
    # Fetch the entry, making sure it blongs to the logged in user
    entry = db.execute(
        'SELECT * FROM entries WHERE id = ? AND user_id = ?',
        (entry_id, session['user_id'])
    ).fetchone()

    if entry:
        return render_template('details.html', entry=entry)
    else:
        flash("Ingredient entry not found!", "error")
        return redirect(url_for('index'))
    
if __name__ == '__main__':
    app.run(debug=True, port=5000)
