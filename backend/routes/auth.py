import os
from flask import Blueprint, request, jsonify, session
from flask_login import login_user, logout_user, login_required, current_user
from backend.database.db import db
from backend.models.models import User, Employee

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/api/auth/check-user', methods=['POST'])
def check_user():
    data = request.get_json() or {}
    identifier = data.get('identifier', '').strip()
    
    if not identifier:
        return jsonify({"error": "Username or email is required"}), 400
        
    user = User.query.filter(
        (User.email == identifier) | (User.username == identifier)
    ).first()
    
    if user:
        return jsonify({"exists": True, "username": user.username, "email": user.email})
    return jsonify({"exists": False})

@auth_bp.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    identifier = data.get('identifier', '').strip()
    password = data.get('password', '')
    
    if not identifier or not password:
        return jsonify({"error": "Missing fields"}), 400
        
    user = User.query.filter(
        (User.email == identifier) | (User.username == identifier)
    ).first()
    
    if not user:
        return jsonify({
            "error": "No account found. Create one.",
            "mode_switch": "signup"
        }), 404
        
    if not user.check_password(password):
        return jsonify({"error": "Invalid credentials"}), 401
        
    login_user(user, remember=True)
    return jsonify({"success": True, "username": user.username})

@auth_bp.route('/api/auth/signup', methods=['POST'])
def signup():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')
    company_name = data.get('company_name', '').strip()
    
    if not username or not email or not password:
        return jsonify({"error": "Missing required fields"}), 400
        
    # Check duplicate username/email
    existing_user = User.query.filter(
        (User.username == username) | (User.email == email)
    ).first()
    if existing_user:
        return jsonify({
            "error": "Account already exists. Please sign in.",
            "mode_switch": "login"
        }), 409
        
    user = User(username=username, email=email, company_name=company_name)
    user.set_password(password)
    
    db.session.add(user)
    db.session.commit()
    
    return jsonify({"success": True, "username": user.username})

@auth_bp.route('/api/auth/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    return jsonify({"success": True})

@auth_bp.route('/api/auth/delete-account', methods=['POST'])
@login_required
def delete_account():
    data = request.get_json() or {}
    password = data.get('password', '')
    
    if not current_user.check_password(password):
        return jsonify({"error": "Incorrect password. Account deletion aborted."}), 401
        
    # Get all employees of user to delete face files
    employees = Employee.query.filter_by(user_id=current_user.id).all()
    for emp in employees:
        if emp.face_path and os.path.exists(emp.face_path):
            try:
                os.remove(emp.face_path)
            except Exception as e:
                # Log error but don't crash
                print(f"Error removing file {emp.face_path}: {e}")
                
    # Delete user from DB (cascades and deletes employees + attendance records)
    db.session.delete(current_user)
    db.session.commit()
    
    logout_user()
    return jsonify({"success": True})

@auth_bp.route('/api/auth/profile', methods=['GET'])
@login_required
def get_profile():
    return jsonify({
        "username": current_user.username,
        "email": current_user.email,
        "full_name": current_user.full_name or "",
        "phone": current_user.phone or "",
        "company_name": current_user.company_name or "",
        "timezone": current_user.timezone or "UTC",
        "profile_picture": current_user.profile_picture or "",
        "email_notifications": current_user.email_notifications,
        "api_key": current_user.api_key or ""
    })

@auth_bp.route('/api/auth/profile', methods=['POST'])
@login_required
def update_profile():
    data = request.get_json() or {}
    full_name = data.get('full_name', '').strip()
    phone = data.get('phone', '').strip()
    company_name = data.get('company_name', '').strip()
    timezone = data.get('timezone', 'UTC').strip()
    email_notifications = bool(data.get('email_notifications', True))
    
    current_user.full_name = full_name
    current_user.phone = phone
    current_user.company_name = company_name
    current_user.timezone = timezone
    current_user.email_notifications = email_notifications
    
    try:
        db.session.commit()
        return jsonify({"success": True, "message": "Profile updated successfully."})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to save profile: {e}"}), 500

@auth_bp.route('/api/auth/profile/password', methods=['POST'])
@login_required
def update_password():
    data = request.get_json() or {}
    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')
    confirm_password = data.get('confirm_password', '')
    
    if not current_password or not new_password or not confirm_password:
        return jsonify({"error": "All password fields are required."}), 400
        
    if not current_user.check_password(current_password):
        return jsonify({"error": "Incorrect current password."}), 400
        
    if new_password != confirm_password:
        return jsonify({"error": "New password and confirmation do not match."}), 400
        
    if len(new_password) < 6:
        return jsonify({"error": "Password must be at least 6 characters long."}), 400
        
    current_user.set_password(new_password)
    try:
        db.session.commit()
        return jsonify({"success": True, "message": "Password updated successfully."})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to update password: {e}"}), 500

@auth_bp.route('/api/auth/profile/picture', methods=['POST'])
@login_required
def upload_avatar():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded."}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected."}), 400
        
    # Ensure directories exist
    avatars_dir = os.path.join('backend', 'static', 'avatars')
    if not os.path.exists(avatars_dir):
        os.makedirs(avatars_dir)
        
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ('.jpg', '.jpeg', '.png', '.gif'):
        return jsonify({"error": "Allowed formats: JPG, JPEG, PNG, GIF"}), 400
        
    import uuid
    filename = f"avatar_{current_user.id}_{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(avatars_dir, filename)
    
    try:
        # Remove old avatar if exists
        if current_user.profile_picture:
            old_path = current_user.profile_picture.lstrip('/')
            if os.path.exists(old_path):
                os.remove(old_path)
    except Exception:
        pass
        
    file.save(filepath)
    db_path = f"/static/avatars/{filename}"
    current_user.profile_picture = db_path
    
    try:
        db.session.commit()
        return jsonify({"success": True, "profile_picture": db_path, "message": "Profile picture updated."})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to save profile picture: {e}"}), 500

@auth_bp.route('/api/auth/profile/api-key', methods=['POST'])
@login_required
def rotate_api_key():
    import uuid
    new_key = f"wp_live_{uuid.uuid4().hex}"
    current_user.api_key = new_key
    try:
        db.session.commit()
        return jsonify({"success": True, "api_key": new_key, "message": "API key rotated successfully."})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to rotate API key: {e}"}), 500
