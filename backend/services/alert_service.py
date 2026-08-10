import os
import uuid
from datetime import datetime
import cv2
from backend.database.db import db
from backend.models.models import Alert, User

class AlertService:
    @staticmethod
    def process_alert(data, frame=None, face_roi=None):
        """Processes and saves an alert event, checking for complex security correlations."""
        user_id = data["user_id"]
        type_ = data["type"]
        severity = data["severity"]
        camera = data.get("camera", "Entrance Cam 1")
        employee_id = data.get("employee_id")
        track_id = data.get("track_id")
        confidence = data.get("confidence", 100.0)
        description = data["description"]
        timestamp = data.get("timestamp", datetime.utcnow())
        zone_name = data.get("zone_name")

        # Save snapshot frame to file if provided
        snapshot_path = None
        if frame is not None:
            try:
                snap_dir = os.path.join('backend', 'static', 'snapshots')
                if not os.path.exists(snap_dir):
                    os.makedirs(snap_dir)
                filename = f"alert_{uuid.uuid4().hex}.jpg"
                filepath = os.path.join(snap_dir, filename)
                cv2.imwrite(filepath, frame)
                snapshot_path = f"/static/snapshots/{filename}"
            except Exception as e:
                print(f"Error saving alert snapshot frame: {e}")

        # Save face crop image to file if provided
        face_crop_path = None
        if face_roi is not None and face_roi.size > 0:
            try:
                snap_dir = os.path.join('backend', 'static', 'snapshots')
                if not os.path.exists(snap_dir):
                    os.makedirs(snap_dir)
                filename = f"crop_{uuid.uuid4().hex}.jpg"
                filepath = os.path.join(snap_dir, filename)
                cv2.imwrite(filepath, face_roi)
                face_crop_path = f"/static/snapshots/{filename}"
            except Exception as e:
                print(f"Error saving alert face crop: {e}")

        # Check Security Escapes/Correlations (e.g. Burglary attempt)
        admin = User.query.get(user_id)
        if admin:
            is_closed = AlertService.is_business_closed(admin)
            
            # Complex rule correlation:
            # Face Hidden/Covered OR Restricted Area breach + Business Closed
            if is_closed and type_ in ("restricted_area", "face_hidden", "restricted_zone_intrusion"):
                type_ = "restricted_zone_intrusion"
                severity = "emergency"
                description = f"CRITICAL SECURITY ALERT: Possible Burglary Attempt! Restricted zone breach in '{zone_name}' while business is CLOSED."
        
        camera_id = data.get("camera_id")

        alert = Alert(
            user_id=user_id,
            employee_id=employee_id,
            camera_id=camera_id,
            track_id=track_id,
            type=type_,
            severity=severity,
            camera=camera,
            confidence=confidence,
            snapshot_path=snapshot_path,
            face_crop_path=face_crop_path,
            zone_name=zone_name,
            duration=0,
            description=description,
            timestamp=timestamp
        )
        db.session.add(alert)
        
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Alert service DB error: {e}")
            
        return alert

    @staticmethod
    def is_business_closed(admin):
        """Helper to verify if current local time is outside business hours."""
        hours_str = admin.business_hours or "09:00-17:00"
        try:
            if '-' not in hours_str:
                return False
            start_str, end_str = hours_str.split('-')
            
            now_time = datetime.now().time()
            
            sh, sm = map(int, start_str.strip().split(':'))
            eh, em = map(int, end_str.strip().split(':'))
            
            start_time = now_time.replace(hour=sh, minute=sm, second=0, microsecond=0)
            end_time = now_time.replace(hour=eh, minute=em, second=0, microsecond=0)
            
            # If standard range e.g. 09:00 to 17:00
            if start_time < end_time:
                return now_time < start_time or now_time > end_time
            else:
                # Overnight e.g. 22:00 to 06:00
                return now_time > end_time and now_time < start_time
        except Exception as e:
            print(f"Error parsing business hours: {e}")
            return False
