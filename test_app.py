import unittest
import os
from app import app, db_service, auth_service  # Replace 'app' with your actual filename if needed

SONG_DIRECTORY = os.path.join(os.getcwd(), "songs_test")

class FlaskAppTests(unittest.TestCase):
    def setUp(self):
        """Setup operations before each test."""
        self.client = app.test_client()
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test_secret_key'
        app.config['DB_PATH'] = 'test.db'

        db_service.db_path = app.config['DB_PATH']
        auth_service.db_path = app.config['DB_PATH']

        db_service.init_db()

        if not os.path.exists(SONG_DIRECTORY):
            os.makedirs(SONG_DIRECTORY)

    def tearDown(self):
        """Cleanup operations after each test."""
        if os.path.exists(db_service.db_path):
            os.remove(db_service.db_path)

        for filename in os.listdir(SONG_DIRECTORY):
            file_path = os.path.join(SONG_DIRECTORY, filename)
            try:
                os.remove(file_path)
            except Exception as e:
                print(f"Failed to delete {file_path}. Reason: {e}")

        with self.client.session_transaction() as sess:
            sess.clear()

    def test_register_user(self):
        """Test user registration functionality."""
        response = self.client.post('/register', json={
            'username': 'testuser',
            'password': 'password123'
        })
        self.assertEqual(response.status_code, 201)
        self.assertIn("User registered successfully", response.get_json().get("message"))

        # Test registering a duplicate user
        response = self.client.post('/register', json={
            'username': 'testuser',
            'password': 'password123'
        })
        self.assertEqual(response.status_code, 409)
        self.assertIn("Username already exists", response.get_json().get("error"))

    def test_login_user(self):
        """Test user login functionality."""
        auth_service.register_user('testuser', 'password123')

        response = self.client.post('/login', json={
            'username': 'testuser',
            'password': 'password123'
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn("Login successful", response.get_json().get("message"))
        with self.client.session_transaction() as sess:
            self.assertIn('user_id', sess)

        # Attempt login with incorrect credentials
        response = self.client.post('/login', json={
            'username': 'testuser',
            'password': 'wrongpassword'
        })
        self.assertEqual(response.status_code, 401)
        self.assertIn("Invalid username or password", response.get_json().get("error"))

    def test_upload_song_as_admin(self):
        """Test uploading a song as an admin user."""
        auth_service.register_user('admin', 'adminpassword')
        self.client.post('/login', json={'username': 'admin', 'password': 'adminpassword'})

        with self.client.session_transaction() as sess:
            sess['user_id'] = 1

        data = {
            'title': 'Test Song',
            'author': 'Test Author',
            'duration': '180'
        }
        response = self.client.post('/upload', data=data, content_type='multipart/form-data')
        self.assertEqual(response.status_code, 400)  # Should fail as no file is provided

        # Assuming a valid 'test.mp3' exists in SONG_DIRECTORY for test purposes
        with open(os.path.join(SONG_DIRECTORY, 'test.mp3'), 'wb') as f:
            f.write(b"fake audio data")

        with open(os.path.join(SONG_DIRECTORY, 'test.mp3'), 'rb') as test_file:
            data['file'] = (test_file, 'test.mp3')
            response = self.client.post('/upload', data=data, content_type='multipart/form-data')
            self.assertEqual(response.status_code, 200)
            self.assertIn("Song uploaded successfully", response.get_json().get("message"))

if __name__ == '__main__':
    unittest.main()
