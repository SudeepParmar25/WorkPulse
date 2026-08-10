from datetime import datetime, date
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from backend.database.db import db

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), default='admin')
    company_name = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # SaaS Profile details
    full_name = db.Column(db.String(100), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    profile_picture = db.Column(db.String(256), nullable=True)
    timezone = db.Column(db.String(50), default='UTC')
    email_notifications = db.Column(db.Boolean, default=True)
    api_key = db.Column(db.String(128), nullable=True)
    
    # Operational configuration / settings
    work_hours_start = db.Column(db.String(10), default='09:00')
    work_hours_end = db.Column(db.String(10), default='17:00')
    break_duration = db.Column(db.Integer, default=60) # in minutes
    late_threshold = db.Column(db.Integer, default=15) # in minutes tolerance
    checkout_timeout = db.Column(db.Integer, default=15) # in seconds absent
    idle_timeout = db.Column(db.Integer, default=15) # in seconds absent
    recognition_threshold = db.Column(db.Float, default=85.0) # distance cutoff
    camera_fps = db.Column(db.Integer, default=20)
    camera_resolution = db.Column(db.String(50), default='640x480')
    camera_settings = db.Column(db.String(100), default='0') # camera source or index
    alert_sensitivity = db.Column(db.String(20), default='medium') # low, medium, high
    business_hours = db.Column(db.String(100), default='09:00-17:00')
    enable_camera_zones = db.Column(db.Boolean, default=False)
    unknown_face_capture_policy = db.Column(db.String(50), default='events_only')
    
    # Relationships
    cameras = db.relationship('Camera', backref='admin', lazy='dynamic', cascade='all, delete-orphan')
    employees = db.relationship('Employee', backref='admin', lazy='dynamic', cascade='all, delete-orphan')
    alerts = db.relationship('Alert', backref='admin', lazy='dynamic', cascade='all, delete-orphan')
    unknown_faces = db.relationship('UnknownFace', backref='admin', lazy='dynamic', cascade='all, delete-orphan')
    customer_counts = db.relationship('CustomerCount', backref='admin', lazy='dynamic', cascade='all, delete-orphan')
    restricted_zones = db.relationship('RestrictedZone', backref='admin', lazy='dynamic', cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Employee(db.Model):
    __tablename__ = 'employees'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    position = db.Column(db.String(100), nullable=False)
    face_path = db.Column(db.String(256), nullable=True) # Primary face snap path
    face_embedding = db.Column(db.Text, nullable=True) # Serialized list of floats
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Uniform specs & categorization
    department = db.Column(db.String(100), nullable=True)
    uniform_color = db.Column(db.String(50), nullable=True) # e.g. 'Blue', 'Black'
    uniform_type = db.Column(db.String(50), nullable=True) # e.g. 'T-Shirt', 'Apron'
    apron_color = db.Column(db.String(50), nullable=True)
    hat = db.Column(db.Boolean, default=False)
    
    # Custom Shift parameters
    shift_start = db.Column(db.String(10), default="09:00")
    shift_end = db.Column(db.String(10), default="17:00")
    
    # Relationships
    attendance_records = db.relationship('Attendance', backref='employee', lazy='dynamic', cascade='all, delete-orphan')
    face_images = db.relationship('EmployeeFaceImage', backref='employee', lazy='dynamic', cascade='all, delete-orphan')

class EmployeeFaceImage(db.Model):
    """Holds multiple registered face samples per employee (front, profile, smile, etc)."""
    __tablename__ = 'employee_face_images'
    
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    face_path = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Attendance(db.Model):
    __tablename__ = 'attendance'
    
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    date = db.Column(db.Date, default=date.today, index=True)
    check_in = db.Column(db.DateTime, nullable=True)
    check_out = db.Column(db.DateTime, nullable=True)
    
    # Metrics (seconds)
    active_time = db.Column(db.Integer, default=0)
    idle_time = db.Column(db.Integer, default=0)
    break_time = db.Column(db.Integer, default=0)
    phone_time = db.Column(db.Integer, default=0)
    
    score = db.Column(db.Float, default=100.0)
    late = db.Column(db.Boolean, default=False)
    
    def calculate_score(self):
        total_time = self.active_time + self.idle_time
        if total_time > 0:
            self.score = round((self.active_time / total_time) * 100.0, 1)
        else:
            self.score = 100.0

class Alert(db.Model):
    """Real-time Event Engine table representing security and operations alerts."""
    __tablename__ = 'alerts'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=True)
    camera_id = db.Column(db.Integer, db.ForeignKey('cameras.id'), nullable=True)
    track_id = db.Column(db.Integer, nullable=True) # centoid tracker id
    
    type = db.Column(db.String(50), nullable=False) 
    severity = db.Column(db.String(20), default='info') # info, warning, critical, emergency
    camera = db.Column(db.String(50), default='Entrance Cam 1')
    confidence = db.Column(db.Float, default=100.0)
    snapshot_path = db.Column(db.String(256), nullable=True) # Crop/snapshot filepath
    face_crop_path = db.Column(db.String(256), nullable=True) # Separate face crop path
    zone_name = db.Column(db.String(100), nullable=True) # Intrusion zone name
    duration = db.Column(db.Integer, default=0) # Duration in seconds
    description = db.Column(db.String(256), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    # Relationship for easy employee data query
    employee_rel = db.relationship('Employee', backref='alerts', lazy=True)

class CustomerCount(db.Model):
    """Tracks foot traffic statistics over time."""
    __tablename__ = 'customer_counts'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    count = db.Column(db.Integer, default=0)

class UnknownFace(db.Model):
    """Stores face crops of unrecognized individuals for registration later."""
    __tablename__ = 'unknown_faces'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    face_path = db.Column(db.String(256), nullable=False)
    appearances = db.Column(db.Integer, default=1)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    camera_name = db.Column(db.String(100), default='Main Camera')
    event_type = db.Column(db.String(50), nullable=True)
    bounding_box = db.Column(db.String(100), nullable=True)
    reason = db.Column(db.String(256), default='Unrecognized Visitor')

class RestrictedZone(db.Model):
    """Stores custom polygonal restricted zone coordinates."""
    __tablename__ = 'restricted_zones'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    camera_id = db.Column(db.Integer, db.ForeignKey('cameras.id'), nullable=True)
    name = db.Column(db.String(100), nullable=False)
    polygon_json = db.Column(db.Text, nullable=False) # JSON encoded coordinate points
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Camera(db.Model):
    __tablename__ = 'cameras'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    source = db.Column(db.String(256), default='0')
    resolution = db.Column(db.String(50), default='640x480')
    fps = db.Column(db.Integer, default=20)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    alerts = db.relationship('Alert', backref='camera_rel', lazy='dynamic', cascade='all, delete-orphan')
    restricted_zones = db.relationship('RestrictedZone', backref='camera_rel', lazy='dynamic', cascade='all, delete-orphan')
