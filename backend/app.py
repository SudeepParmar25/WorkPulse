import os
from flask import Flask, render_template, redirect, url_for
from flask_login import LoginManager, current_user
from backend.config import Config
from backend.database.db import db
from backend.models.models import User
from backend.routes.auth import auth_bp
from backend.routes.camera import camera_bp, camera_manager
from backend.routes.employee import employee_bp
from backend.routes.analytics import analytics_bp
from backend.routes.reports import reports_bp
from backend.routes.settings import settings_bp

def create_app():
    # Templates and static are relative to the 'backend' folder
    app = Flask(__name__, 
                template_folder='templates',
                static_folder='static')
    app.config.from_object(Config)
    
    # Initialize DB
    db.init_app(app)
    
    # Initialize Login Manager
    login_manager = LoginManager()
    login_manager.login_view = 'show_auth'
    login_manager.init_app(app)
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
        
    # Register Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(camera_bp)
    app.register_blueprint(employee_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(settings_bp)
    
    # Root template routing
    @app.route('/')
    def index():
        return render_template('dashboard.html')
        
    @app.route('/auth')
    def show_auth():
        if current_user.is_authenticated:
            return redirect(url_for('index'))
        return render_template('auth.html')
        
    # Bind app context to camera manager for background DB actions
    camera_manager.initialize(app)
    
    # Ensure database tables and upload folders are created
    with app.app_context():
        # Schema migration patch for SQLite
        try:
            import sqlite3
            db_uri = app.config['SQLALCHEMY_DATABASE_URI']
            if db_uri.startswith('sqlite:///'):
                db_name = db_uri.replace('sqlite:///', '')
                db_path = os.path.join(app.root_path, '..', db_name)
                db_path = os.path.abspath(db_path)
                
                if os.path.exists(db_path):
                    conn = sqlite3.connect(db_path)
                    cursor = conn.cursor()
                    cursor.execute("PRAGMA table_info(alerts)")
                    cols = [col[1] for col in cursor.fetchall()]
                    if 'face_crop_path' not in cols:
                        cursor.execute("ALTER TABLE alerts ADD COLUMN face_crop_path VARCHAR(256)")
                    if 'zone_name' not in cols:
                        cursor.execute("ALTER TABLE alerts ADD COLUMN zone_name VARCHAR(100)")
                    if 'duration' not in cols:
                        cursor.execute("ALTER TABLE alerts ADD COLUMN duration INTEGER DEFAULT 0")
                        
                    cursor.execute("PRAGMA table_info(employees)")
                    emp_cols = [col[1] for col in cursor.fetchall()]
                    if 'shift_start' not in emp_cols:
                        cursor.execute("ALTER TABLE employees ADD COLUMN shift_start VARCHAR(10) DEFAULT '09:00'")
                    if 'shift_end' not in emp_cols:
                        cursor.execute("ALTER TABLE employees ADD COLUMN shift_end VARCHAR(10) DEFAULT '17:00'")
                        
                    cursor.execute("PRAGMA table_info(users)")
                    users_cols = [col[1] for col in cursor.fetchall()]
                    if 'unknown_face_capture_policy' not in users_cols:
                        cursor.execute("ALTER TABLE users ADD COLUMN unknown_face_capture_policy VARCHAR(50) DEFAULT 'events_only'")
                    if 'full_name' not in users_cols:
                        cursor.execute("ALTER TABLE users ADD COLUMN full_name VARCHAR(100)")
                    if 'phone' not in users_cols:
                        cursor.execute("ALTER TABLE users ADD COLUMN phone VARCHAR(20)")
                    if 'profile_picture' not in users_cols:
                        cursor.execute("ALTER TABLE users ADD COLUMN profile_picture VARCHAR(256)")
                    if 'timezone' not in users_cols:
                        cursor.execute("ALTER TABLE users ADD COLUMN timezone VARCHAR(50) DEFAULT 'UTC'")
                    if 'email_notifications' not in users_cols:
                        cursor.execute("ALTER TABLE users ADD COLUMN email_notifications BOOLEAN DEFAULT 1")
                    if 'api_key' not in users_cols:
                        cursor.execute("ALTER TABLE users ADD COLUMN api_key VARCHAR(128)")
                        
                    # Generate API keys for users who don't have one
                    cursor.execute("SELECT id, api_key FROM users")
                    for row in cursor.fetchall():
                        uid, key = row
                        if not key:
                            import uuid
                            new_key = f"wp_live_{uuid.uuid4().hex}"
                            cursor.execute("UPDATE users SET api_key = ? WHERE id = ?", (new_key, uid))
                        
                    cursor.execute("PRAGMA table_info(unknown_faces)")
                    unknown_cols = [col[1] for col in cursor.fetchall()]
                    if 'camera_name' not in unknown_cols:
                        cursor.execute("ALTER TABLE unknown_faces ADD COLUMN camera_name VARCHAR(100) DEFAULT 'Main Camera'")
                    if 'event_type' not in unknown_cols:
                        cursor.execute("ALTER TABLE unknown_faces ADD COLUMN event_type VARCHAR(50)")
                    if 'bounding_box' not in unknown_cols:
                        cursor.execute("ALTER TABLE unknown_faces ADD COLUMN bounding_box VARCHAR(100)")
                    if 'reason' not in unknown_cols:
                        cursor.execute("ALTER TABLE unknown_faces ADD COLUMN reason VARCHAR(256) DEFAULT 'Unrecognized Visitor'")
                        
                    # Create cameras table if it doesn't exist
                    cursor.execute("""
                    CREATE TABLE IF NOT EXISTS cameras (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        name VARCHAR(100) NOT NULL,
                        source VARCHAR(256) DEFAULT '0',
                        resolution VARCHAR(50) DEFAULT '640x480',
                        fps INTEGER DEFAULT 20,
                        is_active BOOLEAN DEFAULT 1,
                        created_at DATETIME,
                        FOREIGN KEY(user_id) REFERENCES users(id)
                    )
                    """)
                    
                    # Add camera_id column to restricted_zones if missing
                    cursor.execute("PRAGMA table_info(restricted_zones)")
                    zones_cols = [col[1] for col in cursor.fetchall()]
                    if 'camera_id' not in zones_cols:
                        cursor.execute("ALTER TABLE restricted_zones ADD COLUMN camera_id INTEGER REFERENCES cameras(id)")
                        
                    # Add camera_id column to alerts if missing
                    cursor.execute("PRAGMA table_info(alerts)")
                    alerts_cols = [col[1] for col in cursor.fetchall()]
                    if 'camera_id' not in alerts_cols:
                        cursor.execute("ALTER TABLE alerts ADD COLUMN camera_id INTEGER REFERENCES cameras(id)")
                        
                    # Seed default camera for any user who doesn't have one
                    cursor.execute("SELECT id FROM users")
                    users_list = [row[0] for row in cursor.fetchall()]
                    for uid in users_list:
                        cursor.execute("SELECT id FROM cameras WHERE user_id = ?", (uid,))
                        if not cursor.fetchone():
                            from datetime import datetime
                            cursor.execute("""
                            INSERT INTO cameras (user_id, name, source, resolution, fps, is_active, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            """, (uid, 'Main Cam 1', '0', '640x480', 20, 1, datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')))
                        
                    conn.commit()
                    conn.close()
        except Exception as e:
            print(f"Database schema patch warning: {e}")
            
        db.create_all()
        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            os.makedirs(app.config['UPLOAD_FOLDER'])

            
    return app

app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
