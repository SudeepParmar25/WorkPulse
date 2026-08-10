import os
import base64
import uuid
from flask import Blueprint, request, jsonify, current_app, send_from_directory
from flask_login import login_required, current_user
from sqlalchemy import func
from backend.database.db import db
from backend.models.models import Employee, Attendance, Alert, UnknownFace, EmployeeFaceImage, User
from backend.ai.recognition import face_recognizer_manager

employee_bp = Blueprint('employee', __name__)

def save_base64_image(base64_str, user_id):
    if not base64_str:
        return None
    try:
        if ',' in base64_str:
            base64_str = base64_str.split(',')[1]
        img_data = base64.b64decode(base64_str)
        
        faces_dir = current_app.config['UPLOAD_FOLDER']
        if not os.path.exists(faces_dir):
            os.makedirs(faces_dir)
            
        filename = f"user_{user_id}_{uuid.uuid4().hex}.jpg"
        filepath = os.path.join(faces_dir, filename)
        
        with open(filepath, 'wb') as f:
            f.write(img_data)
            
        return filepath
    except Exception as e:
        print(f"Error saving base64 image: {e}")
        return None

# ==========================================
# EMPLOYEES CRUD
# ==========================================
@employee_bp.route('/api/employees', methods=['GET'])
@login_required
def get_employees():
    employees = Employee.query.filter_by(user_id=current_user.id).all()
    result = []
    for emp in employees:
        records = Attendance.query.filter_by(employee_id=emp.id).all()
        avg_score = sum(r.score for r in records) / len(records) if records else 100.0
        result.append({
            "id": emp.id,
            "name": emp.name,
            "position": emp.position,
            "department": emp.department or "Operations",
            "face_registered": emp.face_path is not None and os.path.exists(emp.face_path),
            "created_at": emp.created_at.strftime("%Y-%m-%d"),
            "attendance_days": len(records),
            "avg_productivity": round(avg_score, 1),
            "uniform_color": emp.uniform_color or "None",
            "uniform_type": emp.uniform_type or "None",
            "apron_color": emp.apron_color or "None",
            "hat": emp.hat or False,
            "shift_start": emp.shift_start or "09:00",
            "shift_end": emp.shift_end or "17:00"
        })
    return jsonify(result)

@employee_bp.route('/api/employees/attendance-logs', methods=['GET'])
@login_required
def get_attendance_logs():
    attendances = Attendance.query.join(Employee).filter(
        Employee.user_id == current_user.id
    ).order_by(Attendance.date.desc(), Attendance.check_in.desc()).all()
    
    logs = []
    for att in attendances:
        logs.append({
            "id": att.id,
            "name": att.employee.name,
            "position": att.employee.position,
            "date": att.date.strftime("%Y-%m-%d"),
            "check_in": att.check_in.strftime("%I:%M:%S %p") if att.check_in else "-",
            "check_out": att.check_out.strftime("%I:%M:%S %p") if att.check_out else "Active Shift",
            "active_time": round(att.active_time / 3600.0, 2),
            "idle_time": round(att.idle_time / 3600.0, 2),
            "phone_time": round(att.phone_time / 3600.0, 2),
            "active_time_raw": att.active_time,
            "idle_time_raw": att.idle_time,
            "phone_time_raw": att.phone_time,
            "late": "Late" if att.late else "On-time",
            "score": att.score
        })
    return jsonify(logs)

@employee_bp.route('/api/employees/search', methods=['GET'])
@login_required
def search_employees():
    q = request.args.get('q', '').strip()
    if not q:
        return get_employees()
        
    employees = Employee.query.filter(
        Employee.user_id == current_user.id,
        (Employee.name.ilike(f'%{q}%')) | (Employee.position.ilike(f'%{q}%')) | (Employee.department.ilike(f'%{q}%'))
    ).all()
    
    result = []
    for emp in employees:
        records = Attendance.query.filter_by(employee_id=emp.id).all()
        avg_score = sum(r.score for r in records) / len(records) if records else 100.0
        result.append({
            "id": emp.id,
            "name": emp.name,
            "position": emp.position,
            "department": emp.department or "Operations",
            "face_registered": emp.face_path is not None and os.path.exists(emp.face_path),
            "created_at": emp.created_at.strftime("%Y-%m-%d"),
            "attendance_days": len(records),
            "avg_productivity": round(avg_score, 1),
            "uniform_color": emp.uniform_color or "None",
            "shift_start": emp.shift_start or "09:00",
            "shift_end": emp.shift_end or "17:00"
        })
    return jsonify(result)

@employee_bp.route('/api/employees/add', methods=['POST'])
@login_required
def add_employee():
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    position = data.get('position', '').strip()
    department = data.get('department', 'Operations').strip()
    
    # Shift parameters
    shift_start = data.get('shift_start', '09:00').strip()
    shift_end = data.get('shift_end', '17:00').strip()
    
    # Uniform specs
    uniform_color = data.get('uniform_color', 'None').strip()
    uniform_type = data.get('uniform_type', 'None').strip()
    apron_color = data.get('apron_color', 'None').strip()
    hat = bool(data.get('hat', False))
    
    image_base64 = data.get('image', '')
    extra_images = data.get('extra_images', []) # Support up to 3 extra face snapshots
    
    if not name or not position:
        return jsonify({"error": "Name and Position are required"}), 400
        
    filepath = None
    if image_base64:
        filepath = save_base64_image(image_base64, current_user.id)
        if not filepath:
            return jsonify({"error": "Failed to process face image"}), 500
            
    emp = Employee(
        user_id=current_user.id,
        name=name,
        position=position,
        department=department,
        uniform_color=uniform_color if uniform_color != "None" else None,
        uniform_type=uniform_type if uniform_type != "None" else None,
        apron_color=apron_color if apron_color != "None" else None,
        hat=hat,
        face_path=filepath,
        shift_start=shift_start,
        shift_end=shift_end
    )
    
    db.session.add(emp)
    db.session.commit()
    
    # Save secondary face snapshots
    for base64_img in extra_images:
        path = save_base64_image(base64_img, current_user.id)
        if path:
            face_img = EmployeeFaceImage(employee_id=emp.id, face_path=path)
            db.session.add(face_img)
            
    db.session.commit()
    
    # Retrain pipeline
    face_recognizer_manager.train_for_user(current_user.id)
    
    return jsonify({
        "success": True, 
        "employee": {"id": emp.id, "name": emp.name}
    })

@employee_bp.route('/api/employees/<int:emp_id>', methods=['PUT', 'DELETE'])
@login_required
def modify_employee(emp_id):
    emp = Employee.query.filter_by(id=emp_id, user_id=current_user.id).first_or_404()
    
    if request.method == 'PUT':
        data = request.get_json() or {}
        name = data.get('name', '').strip()
        position = data.get('position', '').strip()
        department = data.get('department', 'Operations').strip()
        
        # Shift parameters
        shift_start = data.get('shift_start', '09:00').strip()
        shift_end = data.get('shift_end', '17:00').strip()
        
        # Uniform specs
        uniform_color = data.get('uniform_color', 'None').strip()
        uniform_type = data.get('uniform_type', 'None').strip()
        apron_color = data.get('apron_color', 'None').strip()
        hat = bool(data.get('hat', False))
        
        image_base64 = data.get('image', '')
        extra_images = data.get('extra_images', [])
        
        if not name or not position:
            return jsonify({"error": "Name and Position are required"}), 400
            
        emp.name = name
        emp.position = position
        emp.department = department
        emp.uniform_color = uniform_color if uniform_color != "None" else None
        emp.uniform_type = uniform_type if uniform_type != "None" else None
        emp.apron_color = apron_color if apron_color != "None" else None
        emp.hat = hat
        emp.shift_start = shift_start
        emp.shift_end = shift_end
        
        if image_base64:
            if emp.face_path and os.path.exists(emp.face_path):
                try:
                    os.remove(emp.face_path)
                except Exception:
                    pass
            filepath = save_base64_image(image_base64, current_user.id)
            if filepath:
                emp.face_path = filepath
                
        # Handle secondary faces
        if extra_images:
            # Delete old secondary faces
            for old_img in emp.face_images:
                if os.path.exists(old_img.face_path):
                    try:
                        os.remove(old_img.face_path)
                    except Exception:
                        pass
                db.session.delete(old_img)
            
            # Save new ones
            for base64_img in extra_images:
                path = save_base64_image(base64_img, current_user.id)
                if path:
                    face_img = EmployeeFaceImage(employee_id=emp.id, face_path=path)
                    db.session.add(face_img)
                    
        db.session.commit()
        face_recognizer_manager.train_for_user(current_user.id)
        return jsonify({"success": True})
        
    elif request.method == 'DELETE':
        # Nullify associated alerts' employee foreign keys to satisfy constraint check
        try:
            Alert.query.filter_by(employee_id=emp.id).update({Alert.employee_id: None})
            db.session.commit()
        except Exception as e:
            print(f"Error nullifying alerts: {e}")
            
        # Remove primary face crop
        if emp.face_path and os.path.exists(emp.face_path):
            try:
                os.remove(emp.face_path)
            except Exception:
                pass
                
        # Remove extra face crops
        for old_img in emp.face_images:
            if os.path.exists(old_img.face_path):
                try:
                    os.remove(old_img.face_path)
                except Exception:
                    pass
                    
        db.session.delete(emp)
        db.session.commit()
        face_recognizer_manager.train_for_user(current_user.id)
        return jsonify({"success": True})

# ==========================================
# EMPLOYEE PROFILE DETAILS
# ==========================================
@employee_bp.route('/api/employees/faces/<filename>')
@login_required
def serve_face_image(filename):
    faces_dir = current_app.config['UPLOAD_FOLDER']
    return send_from_directory(faces_dir, filename)

@employee_bp.route('/api/employees/<int:emp_id>/profile', methods=['GET'])
@login_required
def get_employee_profile(emp_id):
    emp = Employee.query.filter_by(id=emp_id, user_id=current_user.id).first_or_404()
    records = Attendance.query.filter_by(employee_id=emp.id).order_by(Attendance.date.desc()).all()
    
    attendance_list = []
    total_active = 0
    total_idle = 0
    late_count = 0
    
    for r in records:
        total_active += r.active_time
        total_idle += r.idle_time
        if r.late:
            late_count += 1
            
        attendance_list.append({
            "date": r.date.strftime("%Y-%m-%d"),
            "check_in": r.check_in.strftime("%H:%M:%S") if r.check_in else "-",
            "check_out": r.check_out.strftime("%H:%M:%S") if r.check_out else "-",
            "active_time": f"{r.active_time // 60}m {r.active_time % 60}s",
            "idle_time": f"{r.idle_time // 60}m {r.idle_time % 60}s",
            "score": r.score,
            "late": r.late
        })
        
    total_sessions = len(records)
    avg_score = sum(r.score for r in records) / total_sessions if total_sessions > 0 else 100.0
    late_pct = round((late_count / total_sessions * 100.0), 1) if total_sessions > 0 else 0.0
    
    total_time_seconds = total_active + total_idle
    idle_pct = round((total_idle / total_time_seconds * 100.0), 1) if total_time_seconds > 0 else 0.0
    
    # Calculate daily, weekly, monthly hours worked
    total_active_hours = round(total_active / 3600.0, 2)
    daily_hours = round(total_active_hours / max(1, total_sessions), 2)
    weekly_hours = round(daily_hours * 5, 2) # simulate standard 5-day week
    monthly_hours = round(daily_hours * 22, 2) # simulate standard 22-day month
    
    # Fetch alerts specific to this employee
    alerts = Alert.query.filter_by(employee_id=emp.id).order_by(Alert.timestamp.desc()).limit(10).all()
    timeline = []
    for a in alerts:
        timeline.append({
            "type": a.type,
            "message": a.description,
            "time": a.timestamp.strftime("%I:%M %p"),
            "date": a.timestamp.strftime("%Y-%m-%d"),
            "severity": a.severity
        })
        
    # Get registered face snapshots (primary + extra face images)
    face_samples = []
    if emp.face_path:
        filename = os.path.basename(emp.face_path)
        face_samples.append(f"/api/employees/faces/{filename}")
    for extra in emp.face_images:
        if extra.face_path:
            filename = os.path.basename(extra.face_path)
            face_samples.append(f"/api/employees/faces/{filename}")
            
    # Weekly shift length labels
    weekly_attendance = []
    import datetime as dt
    today = dt.date.today()
    for i in range(6, -1, -1):
        day = today - dt.timedelta(days=i)
        att_day = Attendance.query.filter_by(employee_id=emp.id, date=day).first()
        weekly_attendance.append({
            "day": day.strftime("%a"),
            "date": day.strftime("%Y-%m-%d"),
            "hours": round((att_day.active_time + att_day.idle_time) / 3600.0, 2) if att_day else 0.0
        })

    # Compute actual recognition confidence from Alert log history
    avg_conf = db.session.query(func.avg(Alert.confidence)).filter(
        Alert.employee_id == emp.id,
        Alert.confidence > 0
    ).scalar()
    rec_confidence = round(avg_conf, 1) if avg_conf else 0.0

    return jsonify({
        "id": emp.id,
        "name": emp.name,
        "position": emp.position,
        "department": emp.department or "Operations",
        "face_registered": emp.face_path is not None and os.path.exists(emp.face_path),
        "created_at": emp.created_at.strftime("%Y-%m-%d"),
        "uniform_color": emp.uniform_color or "None",
        "uniform_type": emp.uniform_type or "None",
        "apron_color": emp.apron_color or "None",
        "hat": emp.hat or False,
        "stats": {
            "total_days": total_sessions,
            "average_productivity": round(avg_score, 1),
            "late_percentage": late_pct,
            "idle_percentage": idle_pct,
            "recognition_confidence": rec_confidence,
            "total_active_hours": total_active_hours,
            "total_idle_hours": round(total_idle / 3600.0, 2),
            "daily_hours": daily_hours,
            "weekly_hours": weekly_hours,
            "monthly_hours": monthly_hours
        },
        "attendance": attendance_list,
        "timeline": timeline,
        "face_samples": face_samples,
        "weekly_attendance": weekly_attendance
    })

# ==========================================
# UNKNOWN FACE GALLERY ENDPOINTS
# ==========================================
@employee_bp.route('/api/employees/unknown-faces', methods=['GET'])
def get_unknown_faces():
    user_id = current_user.id if current_user.is_authenticated else 1
    unknowns = UnknownFace.query.filter_by(user_id=user_id).order_by(UnknownFace.timestamp.desc()).all()
    result = []
    for u in unknowns:
        result.append({
            "id": u.id,
            "face_path": u.face_path,
            "appearances": u.appearances,
            "timestamp": u.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "camera_name": u.camera_name or "Main Camera",
            "event_type": u.event_type or "visitor_detected",
            "bounding_box": u.bounding_box,
            "reason": u.reason or "Unrecognized Visitor"
        })
    return jsonify(result)

@employee_bp.route('/api/employees/unknown-faces/<int:face_id>/register', methods=['POST'])
@login_required
def register_unknown_face(face_id):
    unknown = UnknownFace.query.filter_by(id=face_id, user_id=current_user.id).first_or_404()
    data = request.get_json() or {}
    
    name = data.get('name', '').strip()
    position = data.get('position', '').strip()
    department = data.get('department', 'Operations').strip()
    
    # Shift parameters
    shift_start = data.get('shift_start', '09:00').strip()
    shift_end = data.get('shift_end', '17:00').strip()
    
    uniform_color = data.get('uniform_color', 'None').strip()
    uniform_type = data.get('uniform_type', 'None').strip()
    apron_color = data.get('apron_color', 'None').strip()
    hat = bool(data.get('hat', False))
    
    if not name or not position:
        return jsonify({"error": "Name and Position are required"}), 400
        
    # Relocate physical crop file from unknown_crops directory to faces directory
    old_path = unknown.face_path.lstrip('/')
    faces_dir = current_app.config['UPLOAD_FOLDER']
    if not os.path.exists(faces_dir):
        os.makedirs(faces_dir)
        
    new_filename = f"user_{current_user.id}_{uuid.uuid4().hex}.jpg"
    new_filepath = os.path.join(faces_dir, new_filename)
    
    try:
        os.rename(old_path, new_filepath)
    except Exception as e:
        print(f"Error moving crop file: {e}")
        return jsonify({"error": "Failed to register unknown face crop."}), 500
        
    # Create employee mapping
    emp = Employee(
        user_id=current_user.id,
        name=name,
        position=position,
        department=department,
        uniform_color=uniform_color if uniform_color != "None" else None,
        uniform_type=uniform_type if uniform_type != "None" else None,
        apron_color=apron_color if apron_color != "None" else None,
        hat=hat,
        face_path=new_filepath,
        shift_start=shift_start,
        shift_end=shift_end
    )
    
    db.session.add(emp)
    db.session.delete(unknown)
    db.session.commit()
    
    # Retrain LBPH pipeline
    face_recognizer_manager.train_for_user(current_user.id)
    
    return jsonify({
        "success": True, 
        "employee": {"id": emp.id, "name": emp.name}
    })

@employee_bp.route('/api/employees/unknown-faces/<int:face_id>', methods=['DELETE'])
@login_required
def delete_unknown_face(face_id):
    unknown = UnknownFace.query.filter_by(id=face_id, user_id=current_user.id).first_or_404()
    filepath = unknown.face_path.lstrip('/')
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
        except Exception:
            pass
            
    db.session.delete(unknown)
    db.session.commit()
    return jsonify({"success": True})

@employee_bp.route('/api/employees/unknown-faces/all', methods=['DELETE'])
@login_required
def delete_all_unknown_faces():
    unknowns = UnknownFace.query.filter_by(user_id=current_user.id).all()
    for u in unknowns:
        filepath = u.face_path.lstrip('/')
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except Exception:
                pass
        db.session.delete(u)
    db.session.commit()
    return jsonify({"success": True, "message": "All unknown face profiles cleared."})
