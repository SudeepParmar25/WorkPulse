from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from backend.database.db import db

settings_bp = Blueprint('settings', __name__)

@settings_bp.route('/api/settings/all', methods=['GET', 'POST'])
@login_required
def manage_settings():
    if request.method == 'GET':
        return jsonify({
            "company_name": current_user.company_name or "",
            "work_hours_start": current_user.work_hours_start or "09:00",
            "work_hours_end": current_user.work_hours_end or "17:00",
            "break_duration": current_user.break_duration or 60,
            "late_threshold": current_user.late_threshold or 15,
            "checkout_timeout": current_user.checkout_timeout or 15,
            "idle_timeout": current_user.idle_timeout or 15,
            "recognition_threshold": current_user.recognition_threshold or 85.0,
            "camera_fps": current_user.camera_fps or 20,
            "camera_resolution": current_user.camera_resolution or "640x480",
            "camera_settings": current_user.camera_settings or "0",
            "alert_sensitivity": current_user.alert_sensitivity or "medium",
            "business_hours": current_user.business_hours or "09:00-17:00",
            "enable_camera_zones": current_user.enable_camera_zones or False,
            "unknown_face_capture_policy": current_user.unknown_face_capture_policy or "events_only"
        })
        
    elif request.method == 'POST':
        data = request.get_json() or {}
        
        company_name = data.get('company_name', '').strip()
        work_hours_start = data.get('work_hours_start', '09:00').strip()
        work_hours_end = data.get('work_hours_end', '17:00').strip()
        break_duration = data.get('break_duration', 60)
        late_threshold = data.get('late_threshold', 15)
        checkout_timeout = data.get('checkout_timeout', 15)
        idle_timeout = data.get('idle_timeout', 15)
        recognition_threshold = data.get('recognition_threshold', 85.0)
        camera_fps = data.get('camera_fps', 20)
        camera_resolution = data.get('camera_resolution', '640x480').strip()
        camera_settings = data.get('camera_settings', '0').strip()
        alert_sensitivity = data.get('alert_sensitivity', 'medium').strip()
        business_hours = data.get('business_hours', '09:00-17:00').strip()
        enable_camera_zones = bool(data.get('enable_camera_zones', False))
        unknown_face_capture_policy = data.get('unknown_face_capture_policy', 'events_only').strip()
        
        if not company_name:
            return jsonify({"error": "Company name is required."}), 400
            
        current_user.company_name = company_name
        current_user.work_hours_start = work_hours_start
        current_user.work_hours_end = work_hours_end
        current_user.break_duration = int(break_duration)
        current_user.late_threshold = int(late_threshold)
        current_user.checkout_timeout = int(checkout_timeout)
        current_user.idle_timeout = int(idle_timeout)
        current_user.recognition_threshold = float(recognition_threshold)
        current_user.camera_fps = int(camera_fps)
        current_user.camera_resolution = camera_resolution
        current_user.camera_settings = camera_settings
        current_user.alert_sensitivity = alert_sensitivity
        current_user.business_hours = business_hours
        current_user.enable_camera_zones = enable_camera_zones
        current_user.unknown_face_capture_policy = unknown_face_capture_policy
        
        try:
            db.session.commit()
            return jsonify({"success": True, "message": "Settings updated successfully."})
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": f"Database update failed: {e}"}), 500
