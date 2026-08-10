import os
import cv2
import time
import threading
import uuid
from datetime import datetime, date, timedelta
from flask import Blueprint, Response, jsonify, request
from flask_login import login_required, current_user
from sqlalchemy import func
from backend.database.db import db
from backend.models.models import User, Employee, Attendance, Alert, UnknownFace, CustomerCount, RestrictedZone
from backend.ai.recognition import AISurveillancePipeline, event_bus
from backend.services.attendance_service import AttendanceService
from backend.services.alert_service import AlertService

camera_bp = Blueprint('camera', __name__)

class CameraManager:
    def __init__(self):
        self.caps = {}          # camera_id -> cap
        self.threads = {}       # camera_id -> thread
        self.runnings = {}      # camera_id -> bool
        self.last_frames = {}   # camera_id -> jpeg frame
        self.last_frames_anon = {} # camera_id -> jpeg frame_anon
        self.client_counts = {} # camera_id -> int
        self.client_counts_anon = {} # camera_id -> int
        self.latest_raw_frames = {} # camera_id -> raw frame
        
        self.lock = threading.Lock()
        self.app = None
        
        # State tracking in-memory
        self.last_seen = {} # user_id -> { employee_id -> timestamp }
        self.emp_states = {} # user_id -> { employee_id -> 'Active'/'Idle'/'CheckedOut' }
        self.track_saved_unknown = set()
        
        self.unknowns_per_camera = {}
        self.customers_per_camera = {}
        self.current_unknowns_count = 0
        self.current_customers_count = 0
        self.seen_unknown_tracks_today = set()
        self.unknown_entries_today_count = 0
        self.last_stats_reset_date = None
        self.manual_capture_requested = False
        self.track_start_times = {}
        self.last_db_update = 0
        self.last_customer_count_update = 0
        self.listeners_registered = False

    def initialize(self, app):
        self.app = app
        self._register_event_listeners()

    def _register_event_listeners(self):
        if self.listeners_registered:
            return
            
        @event_bus.subscribe("behaviour_event")
        def handle_behaviour_event(data):
            with self.app.app_context():
                AlertService.process_alert(data, frame=data.get("frame"))

        @event_bus.subscribe("attendance_checkin")
        def handle_attendance_checkin(data):
            with self.app.app_context():
                AttendanceService.check_in_employee(data["user_id"], data["employee_id"])

        @event_bus.subscribe("attendance_checkout")
        def handle_attendance_checkout(data):
            with self.app.app_context():
                AttendanceService.check_out_employee(data["user_id"], data["employee_id"], data["last_seen"])

        self.listeners_registered = True
        print("Event Bus listeners bound to Attendance and Alert services.")

    def _reader_loop(self, camera_id):
        cap = self.caps.get(camera_id)
        if not cap:
            return
        # Set buffer size to 1 to minimize WiFi stream frame buffering delay
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass
            
        while self.runnings.get(camera_id) and cap.isOpened():
            try:
                ret, frame = cap.read()
                if ret:
                    self.latest_raw_frames[camera_id] = frame
                else:
                    time.sleep(0.01)
            except Exception as e:
                print(f"Reader loop error on camera {camera_id}: {e}")
                time.sleep(0.05)

    def start(self, user_id, camera_id):
        with self.lock:
            if self.runnings.get(camera_id):
                return True
                
            # Fetch camera configurations from database
            source = '0'
            width, height = 640, 480
            fps = 20
            with self.app.app_context():
                from backend.models.models import Camera
                cam = Camera.query.filter_by(id=camera_id, user_id=user_id).first()
                if not cam:
                    # Fallback to user default settings
                    admin = User.query.get(user_id)
                    if admin:
                        source = admin.camera_settings or '0'
                        res = admin.camera_resolution or "640x480"
                        fps = admin.camera_fps or 20
                        if "x" in res:
                            try:
                                parts = res.split("x")
                                width = int(parts[0])
                                height = int(parts[1])
                            except Exception:
                                pass
                else:
                    source = cam.source or '0'
                    res = cam.resolution or '640x480'
                    fps = cam.fps or 20
                    if "x" in res:
                        try:
                            parts = res.split("x")
                            width = int(parts[0])
                            height = int(parts[1])
                        except Exception:
                            pass
            
            try:
                src = int(source)
            except ValueError:
                src = source # RTSP URL or video path string
            
            # Initialize camera hardware
            cap = cv2.VideoCapture(src, cv2.CAP_DSHOW) if (isinstance(src, int) and os.name == 'nt') else cv2.VideoCapture(src)
            if not cap.isOpened():
                print(f"Camera start error: Could not access hardware capture for camera {camera_id} at source {source}.")
                return False
                
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            
            self.caps[camera_id] = cap
            self.runnings[camera_id] = True
            self.latest_raw_frames[camera_id] = None
            
            from backend.ai.recognition import face_recognizer_manager
            with self.app.app_context():
                face_recognizer_manager.train_for_user(user_id)
                
            # Start non-blocking raw frame reader thread
            reader_thread = threading.Thread(target=self._reader_loop, args=(camera_id,), daemon=True)
            reader_thread.start()
            
            # Start processing thread (passing target resolution width & height)
            thread = threading.Thread(target=self._capture_loop, args=(user_id, camera_id, fps, width, height), daemon=True)
            self.threads[camera_id] = thread
            thread.start()
            print(f"Surveillance loop running for User {user_id}, Camera {camera_id}")
            return True

    def stop(self, camera_id):
        with self.lock:
            self.runnings[camera_id] = False
            cap = self.caps.get(camera_id)
            if cap:
                cap.release()
                self.caps.pop(camera_id, None)
            self.threads.pop(camera_id, None)
            self.last_frames.pop(camera_id, None)
            self.last_frames_anon.pop(camera_id, None)
            self.latest_raw_frames.pop(camera_id, None)
            print(f"Surveillance loop closed for camera {camera_id}.")

    def get_frame(self, camera_id, anonymous=False):
        return self.last_frames_anon.get(camera_id) if anonymous else self.last_frames.get(camera_id)

    def _capture_loop(self, user_id, camera_id, fps, width, height):
        with self.app.app_context():
            pipeline = AISurveillancePipeline(user_id, camera_id)
            last_loop_time = time.time()
            
            # Fetch user configurations
            admin = User.query.get(user_id)
            checkout_timeout = admin.checkout_timeout or 15
            idle_timeout = admin.idle_timeout or 15
            recognition_threshold = admin.recognition_threshold or 85.0
            unknown_face_capture_policy = admin.unknown_face_capture_policy or 'events_only'
            last_settings_load = time.time()
            
            with self.lock:
                if user_id not in self.last_seen:
                    self.last_seen[user_id] = {}
                if user_id not in self.emp_states:
                    self.emp_states[user_id] = {}
            
            while self.runnings.get(camera_id):
                raw_frame = self.latest_raw_frames.get(camera_id)
                if raw_frame is None:
                    time.sleep(0.03)
                    continue
                
                # Resize raw frame to target resolution with high-quality INTER_AREA downscaling
                fh, fw = raw_frame.shape[:2]
                if fw != width or fh != height:
                    frame = cv2.resize(raw_frame, (width, height), interpolation=cv2.INTER_AREA)
                else:
                    frame = raw_frame.copy()
                    
                now = time.time()
                
                # Midnight stats reset check
                try:
                    today_date = date.today()
                    if self.last_stats_reset_date != today_date:
                        self.seen_unknown_tracks_today = set()
                        self.unknown_entries_today_count = 0
                        self.last_stats_reset_date = today_date
                except Exception as ex:
                    print(f"Error resetting statistics: {ex}")
                
                # Dynamic settings update check (every 10 seconds)
                if now - last_settings_load >= 10.0:
                    try:
                        admin_refresh = User.query.get(user_id)
                        if admin_refresh:
                            checkout_timeout = admin_refresh.checkout_timeout or 15
                            idle_timeout = admin_refresh.idle_timeout or 15
                            recognition_threshold = admin_refresh.recognition_threshold or 85.0
                            unknown_face_capture_policy = admin_refresh.unknown_face_capture_policy or 'events_only'
                        last_settings_load = now
                    except Exception as ex:
                        print(f"Error reloading thread settings parameters: {ex}")
                        
                elapsed = now - last_loop_time
                last_loop_time = now
                
                frame = cv2.flip(frame, 1)
                
                # Execute Pipeline
                frame, frame_anon, pipeline_results = pipeline.process_frame(frame, recognition_threshold=recognition_threshold)
                
                current_active_staff_ids = set()
                unknowns_in_frame = 0
                customers_in_frame = 0
                
                for obj in pipeline_results:
                    track_id = obj["track_id"]
                    classification = obj["classification"]
                    emp_id = classification["employee_id"]
                    category = classification["category"]
                    face_visible = obj["face_visible"]
                    
                    if emp_id:
                        # Recognized employee
                        current_active_staff_ids.add(emp_id)
                        with self.lock:
                            self.last_seen[user_id][emp_id] = now
                        
                        prev_state = self.emp_states[user_id].get(emp_id, "CheckedOut")
                        if prev_state == "CheckedOut":
                            with self.lock:
                                self.emp_states[user_id][emp_id] = "Active"
                            event_bus.publish("attendance_checkin", {
                                "user_id": user_id, "employee_id": emp_id
                            })
                        elif prev_state == "Idle":
                            with self.lock:
                                self.emp_states[user_id][emp_id] = "Active"
                            
                        phone_detected = obj.get("phone_detected", False)
                        # Accumulate work hours in service (does not hit DB immediately)
                        AttendanceService.accumulate_time(
                            emp_id, 
                            active_delta=elapsed, 
                            phone_delta=elapsed if phone_detected else 0.0
                        )
                    else:
                        if category == "Customer":
                            customers_in_frame += 1
                        else:
                            unknowns_in_frame += 1
                            if track_id not in self.seen_unknown_tracks_today:
                                self.seen_unknown_tracks_today.add(track_id)
                                self.unknown_entries_today_count += 1
                                
                            # Save unrecognized face crops based on settings policy
                            policy = unknown_face_capture_policy
                            if policy != 'never' and track_id not in self.track_saved_unknown:
                                should_save = False
                                save_reason = "Unrecognized Visitor"
                                save_event_type = "visitor_detected"
                                
                                is_in_restricted_zone = obj["zone"] not in ("Entrance", "Counter", "Kitchen")
                                phone_detected = obj.get("phone_detected", False)
                                
                                # Track duration
                                if track_id not in self.track_start_times:
                                    self.track_start_times[track_id] = now
                                track_dur = now - self.track_start_times[track_id]
                                
                                if policy == 'always':
                                    should_save = True
                                    save_reason = "Always Save Policy"
                                    save_event_type = "always_save"
                                elif policy == 'events_only':
                                    if is_in_restricted_zone:
                                        should_save = True
                                        save_reason = f"Restricted Zone Intrusion: {obj['zone']}"
                                        save_event_type = "restricted_zone_intrusion"
                                    elif phone_detected:
                                        should_save = True
                                        save_reason = "Mobile Phone Usage"
                                        save_event_type = "phone_usage"
                                    elif track_dur >= 30.0:
                                        should_save = True
                                        save_reason = "Prolonged presence (>30 seconds) in view"
                                        save_event_type = "long_presence"
                                    elif self.manual_capture_requested:
                                        should_save = True
                                        save_reason = "Manual Capture by Admin"
                                        save_event_type = "manual_capture"
                                        
                                if should_save and face_visible:
                                    face_box = obj.get("face_box")
                                    if face_box:
                                        self._save_unknown_face_crop(
                                            frame, face_box, user_id, is_face=True,
                                            camera_name=pipeline.camera_name,
                                            event_type=save_event_type,
                                            bounding_box=face_box,
                                            reason=save_reason
                                        )
                                    else:
                                        self._save_unknown_face_crop(
                                            frame, obj["box"], user_id, is_face=False,
                                            camera_name=pipeline.camera_name,
                                            event_type=save_event_type,
                                            bounding_box=obj["box"],
                                            reason=save_reason
                                        )
                                    self.track_saved_unknown.add(track_id)
                            
                with self.lock:
                    self.unknowns_per_camera[camera_id] = unknowns_in_frame
                    self.customers_per_camera[camera_id] = customers_in_frame
                    self.current_unknowns_count = sum(self.unknowns_per_camera.values())
                    self.current_customers_count = sum(self.customers_per_camera.values())
                
                # Verify absentees
                for emp_id, last_time in list(self.last_seen[user_id].items()):
                    if emp_id in current_active_staff_ids:
                        continue
                        
                    time_since_seen = now - last_time
                    current_state = self.emp_states[user_id].get(emp_id, "CheckedOut")
                    
                    if current_state in ("Active", "Idle"):
                        if time_since_seen >= checkout_timeout:
                            with self.lock:
                                self.emp_states[user_id][emp_id] = "CheckedOut"
                            event_bus.publish("attendance_checkout", {
                                "user_id": user_id, "employee_id": emp_id, "last_seen": last_time
                            })
                        elif time_since_seen >= idle_timeout:
                            if current_state == "Active":
                                with self.lock:
                                    self.emp_states[user_id][emp_id] = "Idle"
                                self._trigger_idle_event(user_id, emp_id, pipeline.camera_name)
                            AttendanceService.accumulate_time(emp_id, idle_delta=elapsed)

                # Periodically log customers
                if now - self.last_customer_count_update >= 15.0:
                    if self.current_customers_count > 0:
                        cc = CustomerCount(
                            user_id=user_id,
                            count=self.current_customers_count,
                            timestamp=datetime.utcnow()
                        )
                        db.session.add(cc)
                    self.last_customer_count_update = now

                # Commit changes periodically
                if now - self.last_db_update >= 3.0:
                    try:
                        db.session.commit()
                        self.last_db_update = now
                    except Exception as e:
                        db.session.rollback()
                        print(f"Surveillance database commit error: {e}")

                # Clean up old tracks from start times
                try:
                    current_track_ids = {o["track_id"] for o in pipeline_results}
                    for tid in list(self.track_start_times.keys()):
                        if tid not in current_track_ids:
                            del self.track_start_times[tid]
                except Exception as ex:
                    print(f"Error cleaning track start times: {ex}")
                    
                # Reset manual capture request flag
                self.manual_capture_requested = False

                # Encode normal frame only if normal clients are watching
                if self.client_counts.get(camera_id, 0) > 0:
                    ret_jpeg, jpeg = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
                    if ret_jpeg:
                        self.last_frames[camera_id] = jpeg.tobytes()
                
                # Encode anonymous frame only if anonymous clients are watching
                if self.client_counts_anon.get(camera_id, 0) > 0:
                    ret_jpeg_anon, jpeg_anon = cv2.imencode('.jpg', frame_anon, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
                    if ret_jpeg_anon:
                        self.last_frames_anon[camera_id] = jpeg_anon.tobytes()

                delay = 1.0 / max(1, fps)
                time.sleep(delay)

    def _save_unknown_face_crop(self, frame, box, user_id, is_face=False, camera_name='Main Camera', event_type=None, bounding_box=None, reason='Unrecognized Visitor'):
        try:
            x, y, w, h = box
            fh, fw = frame.shape[:2]
            fx = max(0, x)
            fy = max(0, y)
            fw_crop = min(fw - fx, w)
            if is_face:
                fh_crop = min(fh - fy, h)
            else:
                fh_crop = min(fh - fy, int(h * 0.35))
            
            if fw_crop <= 0 or fh_crop <= 0:
                return
                
            crop = frame[fy:fy+fh_crop, fx:fx+fw_crop]
            if crop.size == 0:
                return
                
            # Verify that a face is actually found in this crop (filters out false positives like shirt creases / patterns)
            if not is_face:
                gray_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
                cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
                cascade = cv2.CascadeClassifier(cascade_path)
                faces_in_crop = cascade.detectMultiScale(gray_crop, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
                if len(faces_in_crop) == 0:
                    return
                
            static_dir = os.path.join('backend', 'static', 'unknown_crops')
            if not os.path.exists(static_dir):
                os.makedirs(static_dir)
                
            filename = f"unknown_{uuid.uuid4().hex}.jpg"
            filepath = os.path.join(static_dir, filename)
            cv2.imwrite(filepath, crop)
            
            db_path = f"/static/unknown_crops/{filename}"
            unknown = UnknownFace(
                user_id=user_id,
                face_path=db_path,
                appearances=1,
                timestamp=datetime.utcnow(),
                camera_name=camera_name,
                event_type=event_type,
                bounding_box=str(bounding_box) if bounding_box else None,
                reason=reason
            )
            db.session.add(unknown)
            db.session.commit()
        except Exception as e:
            print(f"Unknown face crop save error: {e}")

    def _trigger_idle_event(self, user_id, emp_id, camera_name='Main Camera'):
        emp = Employee.query.get(emp_id)
        emp_name = emp.name if emp else f"Staff #{emp_id}"
        event_bus.publish("behaviour_event", {
            "user_id": user_id,
            "employee_id": emp_id,
            "track_id": None,
            "type": "employee_idle",
            "severity": "warning",
            "camera": camera_name,
            "confidence": 100.0,
            "description": f"Engagement: {emp_name} has left their station (marked Idle)",
            "timestamp": datetime.utcnow()
        })

camera_manager = CameraManager()

@camera_bp.route('/api/camera/start', methods=['POST'])
def start_camera():
    user_id = current_user.id if current_user.is_authenticated else 1
    data = request.get_json() or {}
    camera_id = data.get('camera_id')
    if not camera_id:
        from backend.models.models import Camera
        cam = Camera.query.filter_by(user_id=user_id).first()
        camera_id = cam.id if cam else 1
        
    success = camera_manager.start(user_id, camera_id)
    if success:
        return jsonify({"success": True, "message": f"Camera {camera_id} link established."})
    return jsonify({"error": "Could not access hardware camera."}), 500

@camera_bp.route('/api/camera/stop', methods=['POST'])
def stop_camera():
    data = request.get_json() or {}
    camera_id = data.get('camera_id')
    if not camera_id:
        # Stop all running cameras
        for cid in list(camera_manager.runnings.keys()):
            camera_manager.stop(cid)
        return jsonify({"success": True, "message": "All camera links closed."})
    camera_manager.stop(camera_id)
    return jsonify({"success": True, "message": f"Camera link {camera_id} closed."})

@camera_bp.route('/api/camera/status', methods=['GET'])
def camera_status():
    camera_id = request.args.get('camera_id')
    try:
        camera_id = int(camera_id)
    except Exception:
        camera_id = None
        
    if camera_id:
        return jsonify({
            "running": camera_manager.runnings.get(camera_id, False),
            "clients": camera_manager.client_counts.get(camera_id, 0)
        })
    else:
        return jsonify({
            "running": any(camera_manager.runnings.values()),
            "clients": sum(camera_manager.client_counts.values())
        })

def gen_mjpeg_feed(user_id, camera_id, anonymous=False):
    with camera_manager.lock:
        if anonymous:
            if camera_id not in camera_manager.client_counts_anon:
                camera_manager.client_counts_anon[camera_id] = 0
            camera_manager.client_counts_anon[camera_id] += 1
        else:
            if camera_id not in camera_manager.client_counts:
                camera_manager.client_counts[camera_id] = 0
            camera_manager.client_counts[camera_id] += 1
        
    if not camera_manager.runnings.get(camera_id):
        camera_manager.start(user_id, camera_id)
        
    try:
        while camera_manager.runnings.get(camera_id):
            frame_bytes = camera_manager.get_frame(camera_id, anonymous=anonymous)
            if frame_bytes:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            else:
                time.sleep(0.08)
    finally:
        with camera_manager.lock:
            if anonymous:
                if camera_id in camera_manager.client_counts_anon:
                    camera_manager.client_counts_anon[camera_id] = max(0, camera_manager.client_counts_anon[camera_id] - 1)
            else:
                if camera_id in camera_manager.client_counts:
                    camera_manager.client_counts[camera_id] = max(0, camera_manager.client_counts[camera_id] - 1)

@camera_bp.route('/api/camera/feed')
def video_feed():
    is_anon = not current_user.is_authenticated
    user_id = current_user.id if current_user.is_authenticated else 1
    camera_id = request.args.get('camera_id')
    try:
        camera_id = int(camera_id)
    except Exception:
        from backend.models.models import Camera
        # Database fallback (requires context)
        with db.app.app_context():
            cam = Camera.query.filter_by(user_id=user_id).first()
            camera_id = cam.id if cam else 1
            
    return Response(
        gen_mjpeg_feed(user_id, camera_id, anonymous=is_anon),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )

@camera_bp.route('/api/camera/dashboard_live', methods=['GET'])
def get_dashboard_live():
    user_id = current_user.id if current_user.is_authenticated else 1
    today = date.today()
    
    # 1. Fetch live employee statuses from memory states
    states = camera_manager.emp_states.get(user_id, {})
    active_count = sum(1 for s in states.values() if s == "Active")
    idle_count = sum(1 for s in states.values() if s == "Idle")
    
    # Live database queries
    present_count = Attendance.query.join(Employee).filter(
        Employee.user_id == user_id,
        Attendance.date == today,
        Attendance.check_out.is_(None)
    ).count()
    
    unknowns_count = UnknownFace.query.filter_by(user_id=user_id).count()
    
    alerts_today = Alert.query.filter(
        Alert.user_id == user_id,
        db.func.date(Alert.timestamp) == today
    ).count()
    
    phone_alerts_today = Alert.query.filter(
        Alert.user_id == user_id,
        Alert.type == "phone_usage",
        db.func.date(Alert.timestamp) == today
    ).count()
    
    security_alerts_today = Alert.query.filter(
        Alert.user_id == user_id,
        Alert.severity.in_(["critical", "emergency"]),
        db.func.date(Alert.timestamp) == today
    ).count()

    restricted_breaches_today = Alert.query.filter(
        Alert.user_id == user_id,
        Alert.type == "restricted_zone_intrusion",
        db.func.date(Alert.timestamp) == today
    ).count()
    
    # Calculate recognition accuracy from actual confidence levels in DB today
    avg_conf = db.session.query(func.avg(Alert.confidence)).filter(
        Alert.user_id == user_id,
        db.func.date(Alert.timestamp) == today,
        Alert.confidence > 0
    ).scalar()
    
    accuracy_val = round(avg_conf, 1) if avg_conf else 0.0
    
    is_running = any(camera_manager.runnings.values())
    kpis = {
        "current_employees": present_count,
        "current_unknowns": camera_manager.current_unknowns_count if is_running else 0,
        "unknown_entries_today": camera_manager.unknown_entries_today_count if is_running else 0,
        "total_unknowns": unknowns_count,
        "customers": camera_manager.current_customers_count if is_running else 0,
        "working_employees": active_count,
        "idle_employees": idle_count,
        "phone_alerts": phone_alerts_today,
        "security_alerts": security_alerts_today,
        "restricted_breaches": restricted_breaches_today,
        "recognition_accuracy": accuracy_val,
        "camera_status": "Online" if is_running else "Offline"
    }
    
    # 2. Live Alerts Feed
    alerts_query = Alert.query.filter_by(user_id=user_id).order_by(Alert.timestamp.desc()).limit(10).all()
    alerts_list = []
    for a in alerts_query:
        alerts_list.append({
            "id": a.id,
            "type": a.type,
            "severity": a.severity,
            "camera": a.camera,
            "confidence": a.confidence,
            "snapshot_path": a.snapshot_path,
            "face_crop_path": a.face_crop_path,
            "duration": a.duration,
            "description": a.description,
            "timestamp": a.timestamp.strftime("%I:%M:%S %p")
        })
        
    # 3. Live Timeline Feed
    timeline_list = []
    for a in alerts_query:
        timeline_list.append({
            "id": a.id,
            "message": a.description,
            "severity": a.severity,
            "time": a.timestamp.strftime("%I:%M %p"),
            "date": a.timestamp.strftime("%Y-%m-%d")
        })
        
    # 4. Active Employees Table Grid
    attendances = Attendance.query.join(Employee).filter(
        Employee.user_id == user_id,
        Attendance.date == today
    ).all()
    
    active_employees_list = []
    for att in attendances:
        emp = att.employee
        state = states.get(emp.id, "CheckedOut")
        
        # Determine if employee is working overtime
        is_overtime = False
        if att.check_in and not att.check_out and state in ("Active", "Idle"):
            if emp.shift_end:
                try:
                    now_local = datetime.now().time()
                    shift_end_time = datetime.strptime(emp.shift_end, "%H:%M").time()
                    if now_local > shift_end_time:
                        is_overtime = True
                except Exception:
                    pass
                    
        active_employees_list.append({
            "id": emp.id,
            "name": emp.name,
            "position": emp.position,
            "department": emp.department or "Operations",
            "state": state,
            "check_in": att.check_in.strftime("%I:%M:%S %p") if att.check_in else "-",
            "active_time": f"{att.active_time // 60}m",
            "idle_time": f"{att.idle_time // 60}m",
            "score": att.score,
            "is_overtime": is_overtime,
            "shift_end": emp.shift_end or "17:00"
        })
        
    # 5. Unknown faces gallery preview widgets (recent 6 items)
    unknowns_query = UnknownFace.query.filter_by(user_id=user_id).order_by(UnknownFace.timestamp.desc()).limit(6).all()
    unknowns_preview = []
    for u in unknowns_query:
        unknowns_preview.append({
            "id": u.id,
            "face_path": u.face_path,
            "timestamp": u.timestamp.strftime("%I:%M:%S %p"),
            "appearances": u.appearances
        })
        
    return jsonify({
        "kpis": kpis,
        "alerts": alerts_list,
        "timeline": timeline_list,
        "active_employees": active_employees_list,
        "unknowns_preview": unknowns_preview
    })

# =====================================================================
# RESTRICTED ZONES CRUD ENDPOINTS
# =====================================================================
@camera_bp.route('/api/camera/restricted-zones', methods=['GET', 'POST'])
def manage_restricted_zones():
    user_id = current_user.id if current_user.is_authenticated else 1
    if request.method == 'POST':
        if not current_user.is_authenticated:
            return jsonify({"error": "Login required to add zones."}), 401
        data = request.get_json() or {}
        name = data.get('name', '').strip()
        points = data.get('points', [])
        camera_id = data.get('camera_id')
        
        if not name:
            return jsonify({"error": "Zone name is required."}), 400
        if not points or len(points) < 3:
            return jsonify({"error": "A polygon zone must have at least 3 points."}), 400
            
        import json
        zone = RestrictedZone(
            user_id=user_id,
            camera_id=camera_id,
            name=name,
            polygon_json=json.dumps(points)
        )
        db.session.add(zone)
        db.session.commit()
        return jsonify({"success": True, "zone": {"id": zone.id, "name": zone.name, "points": points, "camera_id": camera_id}})
        
    # GET method
    import json
    camera_id = request.args.get('camera_id')
    if camera_id:
        zones = RestrictedZone.query.filter_by(user_id=user_id, camera_id=camera_id).all()
    else:
        zones = RestrictedZone.query.filter_by(user_id=user_id).all()
        
    results = []
    for z in zones:
        try:
            pts = json.loads(z.polygon_json)
        except Exception:
            pts = []
        results.append({
            "id": z.id,
            "name": z.name,
            "points": pts,
            "camera_id": z.camera_id
        })
    return jsonify(results)

@camera_bp.route('/api/camera/restricted-zones/<int:zone_id>', methods=['DELETE'])
@login_required
def delete_restricted_zone(zone_id):
    zone = RestrictedZone.query.filter_by(id=zone_id, user_id=current_user.id).first_or_404()
    db.session.delete(zone)
    db.session.commit()
    return jsonify({"success": True, "message": "Restricted zone deleted."})

@camera_bp.route('/api/camera/restricted-zones/all', methods=['DELETE'])
@login_required
def clear_all_restricted_zones():
    RestrictedZone.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    return jsonify({"success": True, "message": "All restricted zones cleared."})

@camera_bp.route('/api/camera/alerts/<int:alert_id>', methods=['DELETE'])
@login_required
def delete_alert(alert_id):
    alert = Alert.query.filter_by(id=alert_id, user_id=current_user.id).first_or_404()
    db.session.delete(alert)
    db.session.commit()
    return jsonify({"success": True, "message": "Alert log deleted successfully."})

@camera_bp.route('/api/camera/alerts/all', methods=['DELETE'])
@login_required
def delete_all_alerts():
    Alert.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    return jsonify({"success": True, "message": "All alerts cleared successfully."})

@camera_bp.route('/api/camera/manual-capture', methods=['POST'])
def manual_capture_unknown():
    if not any(camera_manager.runnings.values()):
        return jsonify({"error": "Surveillance cameras are offline."}), 400
    if camera_manager.current_unknowns_count == 0:
        return jsonify({"error": "No unrecognized persons currently visible in camera view."}), 400
    
    camera_manager.manual_capture_requested = True
    return jsonify({"success": True, "message": "Manual capture request sent to camera loop."})

# Camera Devices CRUD API
@camera_bp.route('/api/camera/devices', methods=['GET'])
def get_camera_devices():
    from backend.models.models import Camera
    user_id = current_user.id if current_user.is_authenticated else 1
    cameras = Camera.query.filter_by(user_id=user_id).order_by(Camera.created_at.asc()).all()
    # If no cameras exist, seed one automatically for the user
    if not cameras:
        from datetime import datetime
        new_cam = Camera(
            user_id=user_id,
            name='Main Cam 1',
            source='0',
            resolution='640x480',
            fps=20,
            is_active=True,
            created_at=datetime.utcnow()
        )
        db.session.add(new_cam)
        try:
            db.session.commit()
            cameras = [new_cam]
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": f"Failed to seed default camera: {e}"}), 500
            
    # Include thread running state
    result = []
    for cam in cameras:
        result.append({
            "id": cam.id,
            "name": cam.name,
            "source": cam.source,
            "resolution": cam.resolution,
            "fps": cam.fps,
            "is_active": cam.is_active,
            "is_running": camera_manager.runnings.get(cam.id, False)
        })
    return jsonify(result)

@camera_bp.route('/api/camera/devices', methods=['POST'])
@login_required
def add_camera_device():
    from backend.models.models import Camera
    from datetime import datetime
    
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    source = data.get('source', '0').strip()
    resolution = data.get('resolution', '640x480').strip()
    try:
        fps = int(data.get('fps', 20))
    except ValueError:
        fps = 20
        
    if not name:
        return jsonify({"error": "Camera name is required."}), 400
        
    new_cam = Camera(
        user_id=current_user.id,
        name=name,
        source=source,
        resolution=resolution,
        fps=fps,
        is_active=True,
        created_at=datetime.utcnow()
    )
    
    db.session.add(new_cam)
    try:
        db.session.commit()
        return jsonify({
            "success": True, 
            "message": "Camera device added successfully.",
            "device": {
                "id": new_cam.id,
                "name": new_cam.name,
                "source": new_cam.source,
                "resolution": new_cam.resolution,
                "fps": new_cam.fps,
                "is_active": new_cam.is_active
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to add camera: {e}"}), 500

@camera_bp.route('/api/camera/devices/<int:device_id>', methods=['PUT'])
@login_required
def edit_camera_device(device_id):
    from backend.models.models import Camera
    cam = Camera.query.filter_by(id=device_id, user_id=current_user.id).first()
    if not cam:
        return jsonify({"error": "Camera device not found."}), 404
        
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    source = data.get('source', '').strip()
    resolution = data.get('resolution', '').strip()
    fps_val = data.get('fps')
    
    if name:
        cam.name = name
    if source is not None:
        cam.source = source
    if resolution:
        cam.resolution = resolution
    if fps_val is not None:
        try:
            cam.fps = int(fps_val)
        except ValueError:
            pass
            
    # Restart the stream if it was running so new settings take effect
    is_running = camera_manager.runnings.get(cam.id, False)
    if is_running:
        camera_manager.stop(cam.id)
        
    try:
        db.session.commit()
        if is_running:
            camera_manager.start(current_user.id, cam.id)
        return jsonify({"success": True, "message": "Camera device updated successfully."})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to update camera: {e}"}), 500

@camera_bp.route('/api/camera/devices/<int:device_id>', methods=['DELETE'])
@login_required
def delete_camera_device(device_id):
    from backend.models.models import Camera
    cam = Camera.query.filter_by(id=device_id, user_id=current_user.id).first()
    if not cam:
        return jsonify({"error": "Camera device not found."}), 404
        
    # Check that they aren't deleting their last camera
    total_cams = Camera.query.filter_by(user_id=current_user.id).count()
    if total_cams <= 1:
        return jsonify({"error": "Cannot delete the last remaining camera device. Your subscription requires at least one active channel."}), 400
        
    # Stop thread if running
    camera_manager.stop(cam.id)
    
    db.session.delete(cam)
    try:
        db.session.commit()
        return jsonify({"success": True, "message": "Camera device deleted successfully."})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to delete camera: {e}"}), 500

@camera_bp.route('/api/camera/system_devices')
@login_required
def get_system_devices():
    import subprocess
    import json
    
    cameras = []
    try:
        # Query PNP devices of class Camera or Service usbvideo
        cmd = ["powershell", "-Command", "Get-CimInstance Win32_PnPEntity | Where-Object { `$_.PNPClass -eq 'Camera' -or `$_.Service -eq 'usbvideo' } | Select-Object Name | ConvertTo-Json"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if res.returncode == 0 and res.stdout.strip():
            data = json.loads(res.stdout)
            if isinstance(data, dict):
                data = [data]
            names = [d["Name"] for d in data if d and "Name" in d and d["Name"]]
            seen = set()
            unique_names = []
            for n in names:
                if n not in seen:
                    seen.add(n)
                    unique_names.append(n)
            for i, name in enumerate(unique_names):
                cameras.append({"index": str(i), "name": name})
    except Exception as e:
        print(f"Error querying system cameras: {e}")
        
    # If WMI query failed or found no devices, fall back to testing index 0, 1, 2, 3
    if not cameras:
        for i in range(4):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                cameras.append({"index": str(i), "name": f"Webcam Device {i}"})
                cap.release()
                
    return jsonify({"devices": cameras})
