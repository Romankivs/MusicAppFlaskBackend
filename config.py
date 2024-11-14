import os

DB_PATH = 'songs.db'
SONG_DIRECTORY = os.path.join(os.getcwd(), "songs")
MAX_CONTENT_LENGTH = 100 * 1024 * 1024
ALLOWED_EXTENSIONS = {'mp3'}
SECRET_KEY = 'C3zO7bxxx5'