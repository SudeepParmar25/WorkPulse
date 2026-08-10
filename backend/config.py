import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'workpulse-secret-key-1337-prod-saas')
    BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(BASE_DIR, 'workpulse.db')}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Upload folder for face registration
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'faces')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max upload size
