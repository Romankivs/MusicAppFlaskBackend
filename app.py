from flask import Flask, request, jsonify, send_from_directory, abort, session
import sqlite3
import os
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)

# Load configurations from a separate file
app.config.from_pyfile('config.py')

SONG_DIRECTORY = app.config['SONG_DIRECTORY']
ALLOWED_EXTENSIONS = app.config['ALLOWED_EXTENSIONS']
MAX_CONTENT_LENGTH = app.config['MAX_CONTENT_LENGTH']

class DatabaseService:
    """Handles database interactions."""
    
    def __init__(self, db_path):
        self.db_path = db_path
        self.init_db()

    def init_db(self):
        if not os.path.exists(self.db_path):
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS songs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                author TEXT NOT NULL,
                duration INTEGER NOT NULL,
                music_file_url TEXT NOT NULL
            )
            ''')
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL
            )
            ''')
            conn.commit()
            conn.close()

    def add_song(self, title, author, duration, music_file_url):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
        INSERT INTO songs (title, author, duration, music_file_url)
        VALUES (?, ?, ?, ?)
        ''', (title, author, duration, music_file_url))
        song_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return song_id

    def get_song(self, song_id):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT title, author, duration, music_file_url FROM songs WHERE id = ?', (song_id,))
        song = cursor.fetchone()
        conn.close()
        return song

    def get_all_songs(self):
        """Retrieve all songs metadata."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT id, title, author, duration, music_file_url FROM songs')
        songs = cursor.fetchall()
        conn.close()
        return songs

class AuthService:
    """Handles user authentication and authorization."""

    def __init__(self, db_path):
        self.db_path = db_path

    def register_user(self, username, password):
        hashed_password = generate_password_hash(password)
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_password))
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            conn.close()
            return False

    def verify_user(self, username, password):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id, password FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user[1], password):
            return user[0]  # Return user ID on successful authentication
        return None

    def get_username_by_id(self, user_id):
        """Get the username by user_id."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT username FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        conn.close()
        return user[0] if user else None

# Instantiate services
db_service = DatabaseService(app.config['DB_PATH'])
auth_service = AuthService(app.config['DB_PATH'])

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Authentication decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({"error": "Authentication required"}), 401
        return f(*args, **kwargs)
    return decorated_function

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    if auth_service.register_user(username, password):
        return jsonify({"message": "User registered successfully"}), 201
    else:
        return jsonify({"error": "Username already exists"}), 409

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    user_id = auth_service.verify_user(username, password)
    if user_id:
        session['user_id'] = user_id
        return jsonify({"message": "Login successful"}), 200
    else:
        return jsonify({"error": "Invalid username or password"}), 401

@app.route('/logout', methods=['POST'])
@login_required
def logout():
    session.pop('user_id', None)
    return jsonify({"message": "Logged out successfully"}), 200

@app.route('/upload', methods=['POST'])
@login_required
def upload_song():
    # Check if the logged-in user is admin
    user_id = session.get('user_id')
    username = auth_service.get_username_by_id(user_id)
    if username != "admin":
        return jsonify({"error": "You do not have permission to upload songs"}), 403

    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files['file']
    title = request.form.get('title')
    author = request.form.get('author')
    duration = request.form.get('duration')

    if not duration or not duration.isdigit():
        return jsonify({"error": "Invalid duration provided"}), 400

    duration = int(duration)

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(SONG_DIRECTORY, filename)
        file.save(file_path)

        music_file_url = filename
        song_id = db_service.add_song(title, author, duration, music_file_url)

        return jsonify({
            "message": "Song uploaded successfully",
            "id": song_id,
            "title": title,
            "author": author,
            "duration": duration,
            "music_file_url": music_file_url
        }), 200

    return jsonify({"error": "Invalid file format"}), 400

@app.route('/songs/<int:song_id>', methods=['DELETE'])
@login_required
def delete_song(song_id):
    # Check if the logged-in user is admin
    user_id = session.get('user_id')
    username = auth_service.get_username_by_id(user_id)
    if username != "admin":
        return jsonify({"error": "You do not have permission to delete songs"}), 403

    # Try to delete the song from the database
    conn = sqlite3.connect(app.config['DB_PATH'])
    cursor = conn.cursor()
    cursor.execute('SELECT music_file_url FROM songs WHERE id = ?', (song_id,))
    song = cursor.fetchone()

    if song:
        # Remove the song file from the directory
        file_path = os.path.join(SONG_DIRECTORY, song[0])
        if os.path.exists(file_path):
            os.remove(file_path)

        # Remove song from the database
        cursor.execute('DELETE FROM songs WHERE id = ?', (song_id,))
        conn.commit()
        conn.close()
        return jsonify({"message": "Song deleted successfully"}), 200
    else:
        conn.close()
        return jsonify({"error": "Song not found"}), 404

@app.route('/songs/<int:song_id>')
@login_required
def serve_song(song_id):
    song = db_service.get_song(song_id)
    if song:
        song_data = {
            'id': song_id,
            'title': song[0],
            'author': song[1],
            'duration': song[2],
            'music_file_url': song[3]
        }
        return jsonify(song_data)
    else:
        abort(404)

@app.route('/songs', methods=['GET'])
@login_required
def get_all_songs():
    songs = db_service.get_all_songs()
    song_list = []
    for song in songs:
        song_data = {
            'id': song[0],
            'title': song[1],
            'author': song[2],
            'duration': song[3],
            'music_file_url': song[4]
        }
        song_list.append(song_data)
    
    return jsonify(song_list), 200

@app.route('/play/<int:song_id>')
def play_song(song_id):
    song = db_service.get_song(song_id)
    if song:
        song_file = song[3]
        return send_from_directory(SONG_DIRECTORY, song_file, as_attachment=False)
    else:
        abort(404)

if __name__ == "__main__":
    if not os.path.exists(SONG_DIRECTORY):
        os.makedirs(SONG_DIRECTORY)
    app.run(debug=True)
