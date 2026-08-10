import os
from backend.app import create_app
from backend.database.db import db
from backend.models.models import User

def seed_database():
    app = create_app()
    with app.app_context():
        db.drop_all()
        db.create_all()
        
        print("Database tables initialized.")
        
        # Create Default Admin User
        admin = User(
            username="admin",
            email="admin@workpulse.com",
            company_name="WorkPulse Enterprise",
            role="admin",
            work_hours_start="09:00",
            work_hours_end="17:00",
            break_duration=45,
            late_threshold=15,
            checkout_timeout=15,
            idle_timeout=15,
            recognition_threshold=80.0,
            camera_fps=25,
            camera_resolution="640x480",
            alert_sensitivity="medium",
            camera_settings="0",
            business_hours="09:00-17:00",
            enable_camera_zones=False
        )
        admin.set_password("password123")
        db.session.add(admin)
        db.session.commit()
        print("Created default admin user (username: admin, password: password123)")
        print("Database successfully initialized with zero demo/placeholder records.")

if __name__ == '__main__':
    seed_database()
