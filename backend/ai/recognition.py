import os
import cv2
import time
import uuid
import numpy as np
from datetime import datetime
from backend.database.db import db
from backend.models.models import Employee, Alert, UnknownFace, CustomerCount, User, RestrictedZone

# =====================================================================
# INTERNAL EVENT BUS SYSTEM
# =====================================================================
class EventBus:
    """Internal event bus to decouple camera pipeline from database commits."""
    def __init__(self):
        self._listeners = {}

    def subscribe(self, event_type):
        def decorator(callback):
            if event_type not in self._listeners:
                self._listeners[event_type] = []
            self._listeners[event_type].append(callback)
            return callback
        return decorator

    def publish(self, event_type, data):
        if event_type in self._listeners:
            for callback in self._listeners[event_type]:
                try:
                    callback(data)
                except Exception as e:
                    print(f"EventBus error in {event_type} listener: {e}")

# Global Event Bus instance
event_bus = EventBus()

# =====================================================================
# DECOUPLED ABSTRACT SURVEILLANCE INTERFACES (FastAPI/YOLO Pluggable)
# =====================================================================
class BasePersonDetector:
    def detect_people(self, frame):
        """Returns list of boxes as (x, y, w, h) representing whole bodies."""
        raise NotImplementedError

class BasePersonTracker:
    def update(self, rects):
        """Updates tracks. Returns dict of track_id -> (x, y, w, h)"""
        raise NotImplementedError

class BaseFaceRecognizer:
    def train(self, face_samples, labels):
        raise NotImplementedError
    def predict_face(self, user_id, gray_roi):
        """Returns (employee_id, confidence_percentage)"""
        raise NotImplementedError

class BaseUniformClassifier:
    def detect_uniform(self, frame, torso_box):
        """Returns (color_name, confidence)"""
        raise NotImplementedError

class BaseClassifier:
    def classify(self, track_id, body_box, face_res, torso_color):
        raise NotImplementedError

class BaseBehaviourAnalyzer:
    def analyze(self, track_id, category, box, zone, face_visible, now, frame):
        raise NotImplementedError

class BaseAlertEngine:
    def trigger(self, alert_type, severity, camera, employee_id, track_id, confidence, description, snapshot_frame):
        raise NotImplementedError

# =====================================================================
# HAAR CASCADE + LBPH EMBEDDINGS (Core Legacy Support)
# =====================================================================
class HaarCascadeFaceDetector:
    def __init__(self):
        frontal_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        profile_path = cv2.data.haarcascades + 'haarcascade_profileface.xml'
        self.frontal_cascade = cv2.CascadeClassifier(frontal_path)
        self.profile_cascade = cv2.CascadeClassifier(profile_path)
        
    def detect_faces(self, frame, skip_skin_check=False):
        fh, fw = frame.shape[:2]
        
        # Performance Optimization: Downscale search width to 320px for Haar Cascades
        target_w = 320
        if fw > target_w:
            scale = target_w / float(fw)
            target_h = int(fh * scale)
            try:
                small_frame = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_AREA)
                gray_small = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY)
            except Exception:
                scale = 1.0
                gray_small = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            scale = 1.0
            gray_small = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
        min_s = max(20, int(45 * scale))
        
        # 1. Detect frontal faces on optimized small frame
        faces = self.frontal_cascade.detectMultiScale(
            gray_small, scaleFactor=1.1, minNeighbors=8, minSize=(min_s, min_s)
        )
        faces = list(faces)
        
        # 2. Try left profile detection on optimized small frame
        if len(faces) == 0:
            left_profiles = self.profile_cascade.detectMultiScale(
                gray_small, scaleFactor=1.1, minNeighbors=7, minSize=(min_s, min_s)
            )
            faces.extend(list(left_profiles))
            
        # 3. Try right profile detection on optimized small frame
        if len(faces) == 0:
            flipped_gray = cv2.flip(gray_small, 1)
            right_profiles = self.profile_cascade.detectMultiScale(
                flipped_gray, scaleFactor=1.1, minNeighbors=7, minSize=(min_s, min_s)
            )
            for (x, y, w, h) in right_profiles:
                orig_x = target_w - x - w
                faces.append((orig_x, y, w, h))
                
        # Scale bounding box coordinates back to original high-resolution space
        scaled_faces = []
        for (x, y, w, h) in faces:
            orig_x = int(x / scale)
            orig_y = int(y / scale)
            orig_w = int(w / scale)
            orig_h = int(h / scale)
            scaled_faces.append((orig_x, orig_y, orig_w, orig_h))
        faces = scaled_faces
        
        # 4. Suppress overlapping/duplicate face detections (NMS)
        keep_faces = []
        faces = sorted(faces, key=lambda r: r[2] * r[3], reverse=True)
        for r in faces:
            rx, ry, rw, rh = r
            overlap = False
            for k in keep_faces:
                kx, ky, kw, kh = k
                ix = max(rx, kx)
                iy = max(ry, ky)
                iw = min(rx + rw, kx + kw) - ix
                ih = min(ry + rh, ky + kh) - iy
                if iw > 0 and ih > 0:
                    area_i = iw * ih
                    area_r = rw * rh
                    if area_i / float(area_r) > 0.40:
                        overlap = True
                        break
            if not overlap:
                keep_faces.append(r)
        faces = keep_faces
        
        if skip_skin_check:
            return faces
            
        # Detect if image is grayscale (S channel mean is very low)
        try:
            hsv_full = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            if np.mean(hsv_full[:, :, 1]) < 5.0:
                return faces
        except Exception:
            return faces
            
        # Skin tone validation to filter out false positives on walls/textured objects
        valid_faces = []
        for (x, y, w, h) in faces:
            fh, fw = frame.shape[:2]
            x_val = max(0, min(fw - 1, x))
            y_val = max(0, min(fh - 1, y))
            w_val = min(fw - x_val, w)
            h_val = min(fh - y_val, h)
            if w_val <= 0 or h_val <= 0:
                continue
                
            roi = frame[y_val:y_val+h_val, x_val:x_val+w_val]
            try:
                hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
                lower_skin = np.array([0, 8, 40], dtype=np.uint8)
                upper_skin = np.array([30, 170, 255], dtype=np.uint8)
                mask = cv2.inRange(hsv, lower_skin, upper_skin)
                ratio = cv2.countNonZero(mask) / float(roi.shape[0] * roi.shape[1])
                if ratio >= 0.08: # Minimum 8% skin-tone pixels
                    valid_faces.append((x_val, y_val, w_val, h_val))
            except Exception:
                valid_faces.append((x_val, y_val, w_val, h_val))
        return valid_faces

class LBPHFaceRecognizer(BaseFaceRecognizer):
    def __init__(self):
        self.recognizer = cv2.face.LBPHFaceRecognizer_create()
        self.trained = False

    def train(self, face_samples, labels):
        if len(face_samples) > 0:
            self.recognizer.train(face_samples, np.array(labels))
            self.trained = True
            return True
        self.trained = False
        return False

    def predict_face(self, user_id, face_roi):
        # Implementation is wrapped in LegacyFaceRecognizerManager for multi-admin support
        pass

# =====================================================================
# LIGHTWEIGHT CENTROID TRACKER IMPLEMENTATION
# =====================================================================
class CentroidPersonTracker(BasePersonTracker):
    def __init__(self, max_disappeared=40):
        self.next_track_id = 1
        self.tracks = {} # track_id -> centroid
        self.boxes = {} # track_id -> box
        self.disappeared = {} # track_id -> count
        self.max_disappeared = max_disappeared

    def register(self, centroid, box):
        self.tracks[self.next_track_id] = centroid
        self.boxes[self.next_track_id] = box
        self.disappeared[self.next_track_id] = 0
        self.next_track_id += 1

    def deregister(self, track_id):
        del self.tracks[track_id]
        del self.boxes[track_id]
        del self.disappeared[track_id]

    def update(self, rects):
        if len(rects) == 0:
            for track_id in list(self.disappeared.keys()):
                self.disappeared[track_id] += 1
                if self.disappeared[track_id] > self.max_disappeared:
                    self.deregister(track_id)
            return self.boxes

        input_centroids = np.zeros((len(rects), 2), dtype="int")
        for (i, (startX, startY, width, height)) in enumerate(rects):
            cX = int(startX + (width / 2.0))
            cY = int(startY + (height / 2.0))
            input_centroids[i] = (cX, cY)

        if len(self.tracks) == 0:
            for i in range(0, len(input_centroids)):
                self.register(input_centroids[i], rects[i])
        else:
            track_ids = list(self.tracks.keys())
            track_centroids = list(self.tracks.values())

            D = np.linalg.norm(np.array(track_centroids)[:, np.newaxis] - input_centroids, axis=2)

            rows = D.min(axis=1).argsort()
            cols = D.argmin(axis=1)[rows]

            used_rows = set()
            used_cols = set()

            for (row, col) in zip(rows, cols):
                if row in used_rows or col in used_cols:
                    continue

                track_id = track_ids[row]
                self.tracks[track_id] = input_centroids[col]
                self.boxes[track_id] = rects[col]
                self.disappeared[track_id] = 0

                used_rows.add(row)
                used_cols.add(col)

            unused_rows = set(range(0, D.shape[0])).difference(used_rows)
            unused_cols = set(range(0, D.shape[1])).difference(used_cols)

            for row in unused_rows:
                track_id = track_ids[row]
                self.disappeared[track_id] += 1
                if self.disappeared[track_id] > self.max_disappeared:
                    self.deregister(track_id)

            for col in unused_cols:
                self.register(input_centroids[col], rects[col])

        return self.boxes

# =====================================================================
# DETECTOR & UNIFORM COLOR EXTRACTORS
# =====================================================================
class HaarPersonDetector(BasePersonDetector):
    """Detects face boxes and expands them downwards representing whole bodies."""
    def __init__(self, face_detector):
        self.face_detector = face_detector

    def detect_people(self, frame, tracked_objects=None):
        faces = self.face_detector.detect_faces(frame)
        people_boxes = []
        for (x, y, w, h) in faces:
            if tracked_objects:
                is_false_face = False
                for tid, (bx, by, bw, bh) in tracked_objects.items():
                    head_bottom = by + int(bh * 0.25)
                    # If face y starts below head_bottom and is within the x-bounds of the body
                    if (y > head_bottom) and (bx <= x <= bx + bw) and (by <= y <= by + bh):
                        is_false_face = True
                        break
                if is_false_face:
                    continue
                    
            body_y = y
            body_h = h * 4
            body_x = max(0, x - int(w * 0.2))
            body_w = int(w * 1.4)
            people_boxes.append((body_x, body_y, body_w, body_h))
        return people_boxes

class SimpleUniformDetector(BaseUniformClassifier):
    """Extracts average color from upper torso region."""
    def detect_uniform(self, frame, torso_box):
        tx, ty, tw, th = torso_box
        fh, fw = frame.shape[:2]
        tx1 = max(0, min(fw - 1, tx))
        ty1 = max(0, min(fh - 1, ty))
        tx2 = max(0, min(fw - 1, tx + tw))
        ty2 = max(0, min(fh - 1, ty + th))
        
        if tx2 <= tx1 or ty2 <= ty1:
            return "Unknown", 0.0
            
        crop = frame[ty1:ty2, tx1:tx2]
        if crop.size == 0:
            return "Unknown", 0.0

        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        avg_hsv = cv2.mean(hsv)[:3]
        h, s, v = avg_hsv
        
        color_name = "Black"
        if v < 45:
            color_name = "Black"
        elif s < 30 and v > 180:
            color_name = "White"
        elif s < 35:
            color_name = "Gray"
        else:
            if h < 10 or h > 165:
                color_name = "Red"
            elif 10 <= h < 25:
                color_name = "Orange"
            elif 25 <= h < 38:
                color_name = "Yellow"
            elif 38 <= h < 85:
                color_name = "Green"
            elif 85 <= h < 130:
                color_name = "Blue"
            else:
                color_name = "Purple"
                
        return color_name, 100.0

# =====================================================================
# PIECEWISE ORCHESTRATOR
# =====================================================================
class LegacyFaceRecognizerManager(BaseFaceRecognizer):
    """Orchestrates face training and prediction (LBPH matches)."""
    def __init__(self, face_detector):
        self.face_detector = face_detector
        self.recognizer = cv2.face.LBPHFaceRecognizer_create()
        self.trained = False

    def train_for_user(self, user_id):
        # Query registered employees for this user with images
        employees = Employee.query.filter(
            Employee.user_id == user_id,
            Employee.face_path.isnot(None)
        ).all()
        
        face_samples = []
        labels = []
        
        for emp in employees:
            paths = [emp.face_path]
            for extra in emp.face_images:
                if extra.face_path:
                    paths.append(extra.face_path)
            
            for path in paths:
                if not os.path.exists(path):
                    continue
                img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
                if img is None:
                    continue
                faces = self.face_detector.detect_faces(cv2.cvtColor(img, cv2.COLOR_GRAY2BGR), skip_skin_check=True)
                if len(faces) > 0:
                    for (x, y, w, h) in faces:
                        roi = cv2.resize(img[y:y+h, x:x+w], (180, 180))
                        roi = cv2.equalizeHist(roi)
                        face_samples.append(roi)
                        labels.append(emp.id)
                        break
                else:
                    roi = cv2.resize(img, (180, 180))
                    roi = cv2.equalizeHist(roi)
                    face_samples.append(roi)
                    labels.append(emp.id)
                    
        if len(face_samples) > 0:
            self.recognizer.train(face_samples, np.array(labels))
            self.trained = True
        else:
            self.trained = False
            
        print(f"LBPH trained: {self.trained} ({len(face_samples)} face templates)")
        return self.trained

    def predict_face(self, user_id, gray_roi, threshold=85.0):
        if not self.trained:
            return None, 0.0
            
        face_roi = cv2.resize(gray_roi, (180, 180))
        face_roi = cv2.equalizeHist(face_roi)
        try:
            label_id, dist = self.recognizer.predict(face_roi)
            conf = max(0, int((1.0 - (dist / 115.0)) * 100))
            
            # Map threshold (e.g. 85) to dynamic match distance
            max_dist = 115.0 - (threshold - 50.0) * 1.2
            max_dist = max(50.0, min(115.0, max_dist))
            
            if dist <= max_dist:
                # Double-check that employee exists in the database
                emp = Employee.query.filter_by(id=label_id, user_id=user_id).first()
                if emp:
                    display_conf = max(int(threshold), conf)
                    return label_id, display_conf
            return None, conf
        except Exception as e:
            print(f"Prediction error: {e}")
            return None, 0.0

# Instantiate globally
face_recognizer_manager = LegacyFaceRecognizerManager(HaarCascadeFaceDetector())

class HybridClassifier(BaseClassifier):
    """Classifies detected tracks. Uniforms ONLY verify identity, never recognize initially."""
    def __init__(self, user_id):
        self.user_id = user_id
        self.track_classifications = {} # track_id -> employee_id or None
        self.track_rolling_confidence = {} # track_id -> list of float confidences

    def classify(self, track_id, body_box, face_res, torso_color):
        emp_id = face_res.get("employee_id")
        conf = face_res.get("confidence", 0.0)

        # rolling average confidence
        if track_id not in self.track_rolling_confidence:
            self.track_rolling_confidence[track_id] = []
        if conf > 0:
            self.track_rolling_confidence[track_id].append(conf)
            if len(self.track_rolling_confidence[track_id]) > 5:
                self.track_rolling_confidence[track_id].pop(0)
            conf = sum(self.track_rolling_confidence[track_id]) / len(self.track_rolling_confidence[track_id])

        # Query Employee details
        employees = Employee.query.filter_by(user_id=self.user_id).all()
        emp_map = {e.id: e for e in employees}

        # Rule 1: Initial identification MUST be via face recognition
        if emp_id and emp_id in emp_map:
            emp = emp_map[emp_id]
            category = "Manager" if "manager" in emp.position.lower() else "Employee"
            res = {"employee_id": emp_id, "confidence": round(conf, 1), "category": category, "name": emp.name, "position": emp.position}
            self.track_classifications[track_id] = res
            return res

        # Rule 2: If face disappears but uniform matches previously recognized employee, keep tracking them
        if track_id in self.track_classifications:
            prev_res = self.track_classifications[track_id]
            prev_emp_id = prev_res.get("employee_id")
            if prev_emp_id and prev_emp_id in emp_map:
                prev_emp = emp_map[prev_emp_id]
                # If uniform color was not specified OR matches torso color, verify tracking
                if not prev_emp.uniform_color or prev_emp.uniform_color.lower() == torso_color.lower():
                    return prev_res

        # Rule 3: Torso/Uniform alone NEVER recognizes someone initially. They are Unknown
        cx, cy, cw, ch = body_box
        # Check if they are in Counter/Dining zones (proxy for customer status)
        center_x = cx + int(cw / 2)
        
        category = "Customer" if (220 <= center_x < 440) else "Unknown"
        res = {
            "employee_id": None,
            "confidence": 0.0,
            "category": category,
            "name": "Unknown",
            "position": "Visitor"
        }
        self.track_classifications[track_id] = res
        return res

class RuleBasedBehaviorAnalyzer(BaseBehaviourAnalyzer):
    """Monitors behaviors and publishes events without writing to DB directly."""
    def __init__(self, user_id):
        self.user_id = user_id
        self.track_entrance_time = {} # track_id -> timestamp
        self.track_last_alert = {} # alert_type -> timestamp
        self.track_face_lost_time = {} # track_id -> timestamp

    def analyze(self, track_id, classification, box, zone, face_visible, now, frame):
        category = classification["category"]
        emp_id = classification["employee_id"]
        emp_name = classification["name"]

        # 1. Loitering checks - temporarily disabled for security alerts removal
        pass

        # 2. Zone breaches - temporarily disabled for security alerts removal
        pass

        # 3. Face Hidden warnings - temporarily disabled for security alerts removal
        pass

class AISurveillancePipeline:
    def __init__(self, user_id, camera_id=None):
        self.user_id = user_id
        self.camera_id = camera_id
        self.camera_name = "Main Cam 1"
        if camera_id:
            try:
                from backend.models.models import Camera
                cam = Camera.query.get(camera_id)
                if cam:
                    self.camera_name = cam.name
            except Exception:
                pass
        
        # Instantiate stages
        self.face_detector = HaarCascadeFaceDetector()
        self.person_detector = HaarPersonDetector(self.face_detector)
        self.tracker = CentroidPersonTracker()
        self.uniform_detector = SimpleUniformDetector()
        self.classifier = HybridClassifier(user_id)
        self.behavior_analyzer = RuleBasedBehaviorAnalyzer(user_id)
        self.face_recognizer = face_recognizer_manager
        
        # Throttled face recognition map
        self.track_last_recognition = {} # track_id -> timestamp
        self.track_last_face_res = {} # track_id -> last face prediction result
        
        # Active intrusions mapping: (track_id, zone_name) -> {"alert_id": alert.id, "entry_time": timestamp}
        self.active_intrusions = {}
        
        # Custom zones caching parameters
        self.last_zone_load = 0
        self.cached_zones = []
        
        # Shift cache parameters
        self.employee_shifts_cache = {}
        self.last_shift_cache_load = 0
        
        # Cache admin settings on the instance
        self.cached_admin = None
        self.last_admin_load = 0

    def process_frame(self, frame, recognition_threshold=85.0):
        now = time.time()
        frame_anon = frame.copy()
        
        # 1. Person Detector (pass previous frame's tracked boxes to filter false faces on active torsos)
        body_boxes = self.person_detector.detect_people(frame, tracked_objects=self.tracker.boxes)
        
        # 2. Track Centroids
        tracked_objects = self.tracker.update(body_boxes)
        
        # Load user configuration to draw zones dynamically (cached every 10 seconds)
        if (self.cached_admin is None) or (now - self.last_admin_load >= 10.0):
            try:
                self.cached_admin = User.query.get(self.user_id)
                self.last_admin_load = now
            except Exception as e:
                print(f"Error loading admin config cache: {e}")
        admin = self.cached_admin
        fh, fw = frame.shape[:2]
        
        # Load user's custom zones (cached to prevent query flooding / locked db issues)
        if now - self.last_zone_load >= 10.0:
            try:
                if self.camera_id:
                    self.cached_zones = RestrictedZone.query.filter_by(user_id=self.user_id, camera_id=self.camera_id).all()
                else:
                    self.cached_zones = RestrictedZone.query.filter_by(user_id=self.user_id).all()
                self.last_zone_load = now
            except Exception as e:
                print(f"Error loading custom zones: {e}")
                
        # Refresh employee shifts cache (every 10.0 seconds)
        if now - self.last_shift_cache_load >= 10.0:
            try:
                employees = Employee.query.filter_by(user_id=self.user_id).all()
                self.employee_shifts_cache = {e.id: {"shift_start": e.shift_start, "shift_end": e.shift_end} for e in employees}
                self.last_shift_cache_load = now
            except Exception as e:
                print(f"Error loading employee shifts cache: {e}")
                
        import json
        zone_polys = []
        occupied_zones = set()
        
        for zone in self.cached_zones:
            try:
                pts = json.loads(zone.polygon_json)
                if pts:
                    # Convert ratios back to pixels in float32 type for pointPolygonTest
                    pts_pixels = np.array([[pt[0] * fw, pt[1] * fh] for pt in pts], dtype=np.float32)
                    zone_polys.append((zone.name, pts_pixels))
            except Exception as e:
                print(f"Error parsing zone {zone.name}: {e}")
                
        # Centroid zone occupancy mapping
        current_track_zones = {}
        for track_id, box in tracked_objects.items():
            bx, by, bw, bh = box
            cx = bx + int(bw / 2)
            cy = by + int(bh / 2)
            
            for zone_name, pts_pixels in zone_polys:
                try:
                    # CV2 pointPolygonTest contour shape must be (N, 1, 2)
                    dist = cv2.pointPolygonTest(pts_pixels.reshape((-1, 1, 2)), (float(cx), float(cy)), False)
                    if dist >= 0:
                        current_track_zones[track_id] = zone_name
                        occupied_zones.add(zone_name)
                        break
                except Exception as ex:
                    print(f"pointPolygonTest error: {ex}")
                    
        # Draw custom zones
        for zone_name, pts_pixels in zone_polys:
            is_occupied = zone_name in occupied_zones
            color = (0, 0, 255) if is_occupied else (241, 102, 99) # BGR: Red occupied, Indigo empty
            try:
                cv2.polylines(frame, [pts_pixels.astype(np.int32)], isClosed=True, color=color, thickness=2)
                cv2.polylines(frame_anon, [pts_pixels.astype(np.int32)], isClosed=True, color=color, thickness=2)
                if len(pts_pixels) > 0:
                    cv2.putText(frame, f"RESTRICTED: {zone_name}", (int(pts_pixels[0][0]), int(pts_pixels[0][1] - 8)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
                    cv2.putText(frame_anon, f"RESTRICTED: {zone_name}", (int(pts_pixels[0][0]), int(pts_pixels[0][1] - 8)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
            except Exception as ex:
                print(f"Drawing polylines error: {ex}")

        faces_detected = self.face_detector.detect_faces(frame)
        # Filter out false faces located on tracked body torsos/legs
        filtered_faces = []
        for (fx, fy, fw_face, fh_face) in faces_detected:
            is_false_face = False
            for tid, (bx, by, bw, bh) in tracked_objects.items():
                head_bottom = by + int(bh * 0.25)
                if (fy > head_bottom) and (bx <= fx <= bx + bw) and (by <= fy <= by + bh):
                    is_false_face = True
                    break
            if not is_false_face:
                filtered_faces.append((fx, fy, fw_face, fh_face))
        faces_detected = filtered_faces
        
        results = []
        
        for track_id, box in tracked_objects.items():
            bx, by, bw, bh = box
            
            # Map zones (use centroid center detection against custom drawn zones)
            cx_fallback = bx + int(bw / 2)
            if cx_fallback < 220:
                zone = "Entrance"
            elif 220 <= cx_fallback < 440:
                zone = "Counter"
            else:
                zone = "Kitchen"
                
            zone_entered = current_track_zones.get(track_id)
            
            # Torso crop
            torso_y = by + int(bh * 0.25)
            torso_h = int(bh * 0.5)
            torso_box = (bx, torso_y, bw, torso_h)
            torso_color, _ = self.uniform_detector.detect_uniform(frame, torso_box)
            
            # Check overlap face
            overlapping_face = None
            for (fx, fy, fw_face, fh_face) in faces_detected:
                if bx <= fx <= bx + bw and by <= fy <= by + bh:
                    overlapping_face = (fx, fy, fw_face, fh_face)
                    break
                    
            face_res = {"employee_id": None, "confidence": 0.0}
            face_visible = overlapping_face is not None
            
            if face_visible:
                fx, fy, fw_face, fh_face = overlapping_face
                
                # THROTLED RECOGNITION CHECK:
                last_rec_time = self.track_last_recognition.get(track_id, 0)
                last_res = self.track_last_face_res.get(track_id, {})
                last_conf = last_res.get("confidence", 0.0)
                is_conf_employee = last_conf >= 80.0 and last_res.get("employee_id") is not None
                
                if is_conf_employee:
                    face_res = last_res
                elif (track_id not in self.track_last_recognition) or (now - last_rec_time >= 5.0) or (last_conf > 0 and last_conf < 60.0):
                    face_roi_bgr = frame[fy:fy+fh_face, fx:fx+fw_face]
                    if face_roi_bgr.size > 0:
                        face_roi = cv2.cvtColor(face_roi_bgr, cv2.COLOR_BGR2GRAY)
                        emp_id, conf = self.face_recognizer.predict_face(self.user_id, face_roi, threshold=recognition_threshold)
                        face_res = {"employee_id": emp_id, "confidence": conf}
                        self.track_last_recognition[track_id] = now
                        self.track_last_face_res[track_id] = face_res
                else:
                    face_res = last_res if last_res else {"employee_id": None, "confidence": 0.0}

            # Classification step
            classification = self.classifier.classify(track_id, box, face_res, torso_color)
            
            # Behavior step
            self.behavior_analyzer.analyze(track_id, classification, box, zone, face_visible, now, frame)
            
            # Phone usage checks (heuristic visual model)
            phone_detected = False
            if face_visible:
                fx, fy, fw_face, fh_face = overlapping_face
                phone_detected = self.detect_phone_near_face(frame, (fx, fy, fw_face, fh_face))
                
                emp_id = classification["employee_id"]
                emp_name = classification["name"]
                if phone_detected and emp_id:
                    # Check shift hours
                    now_time = datetime.now().time()
                    is_shift_hours = True # default
                    if admin and admin.work_hours_start and admin.work_hours_end:
                        try:
                            start_t = datetime.strptime(admin.work_hours_start, "%H:%M").time()
                            end_t = datetime.strptime(admin.work_hours_end, "%H:%M").time()
                            if start_t <= end_t:
                                is_shift_hours = start_t <= now_time <= end_t
                            else:
                                is_shift_hours = now_time >= start_t or now_time <= end_t
                        except Exception:
                            pass
                            
                    if is_shift_hours:
                        throttle_key = f"phone_usage_{track_id}"
                        # Throttle alert to once every 120 seconds per track
                        if now - self.behavior_analyzer.track_last_alert.get(throttle_key, 0) >= 120.0:
                            event_bus.publish("behaviour_event", {
                                "user_id": self.user_id,
                                "type": "phone_usage",
                                "severity": "warning",
                                "camera": self.camera_name,
                                "camera_id": self.camera_id,
                                "employee_id": emp_id,
                                "track_id": track_id,
                                "confidence": 90.0,
                                "description": f"Engagement Incident: {emp_name} detected using mobile phone during shift hours.",
                                "frame": frame
                            })
                            self.behavior_analyzer.track_last_alert[throttle_key] = now
            
            # Overtime shift exceeded checks
            emp_id = classification["employee_id"]
            emp_name = classification["name"]
            if emp_id and emp_id in self.employee_shifts_cache:
                shift_info = self.employee_shifts_cache[emp_id]
                shift_end_str = shift_info.get("shift_end")
                if shift_end_str:
                    try:
                        now_local = datetime.now().time()
                        shift_end_time = datetime.strptime(shift_end_str, "%H:%M").time()
                        if now_local > shift_end_time:
                            # Trigger warning alert once per day per employee
                            from datetime import date
                            throttle_key = f"overtime_{emp_id}_{date.today().isoformat()}"
                            if now - self.behavior_analyzer.track_last_alert.get(throttle_key, 0) >= 86400.0:
                                event_bus.publish("behaviour_event", {
                                    "user_id": self.user_id,
                                    "type": "overtime_shift_exceeded",
                                    "severity": "warning",
                                    "camera": self.camera_name,
                                    "camera_id": self.camera_id,
                                    "employee_id": emp_id,
                                    "track_id": track_id,
                                    "confidence": 95.0,
                                    "description": f"Overtime Alert: {emp_name} is still working after scheduled shift end of {shift_end_str}.",
                                    "frame": frame
                                })
                                self.behavior_analyzer.track_last_alert[throttle_key] = now
                    except Exception as ex:
                        print(f"Error checking employee overtime: {ex}")
            
            # Restricted zone intrusion detection logic
            if zone_entered:
                intrusion_key = (track_id, zone_entered)
                if intrusion_key not in self.active_intrusions:
                    emp_id = classification["employee_id"]
                    emp_name = classification["name"]
                    
                    description = f"Security Breach: Person entered restricted zone '{zone_entered}'."
                    if emp_id:
                        description = f"Security Breach: Staff member {emp_name} entered restricted zone '{zone_entered}'."
                        
                    alert_data = {
                        "user_id": self.user_id,
                        "type": "restricted_zone_intrusion",
                        "severity": "critical",
                        "camera": self.camera_name,
                        "camera_id": self.camera_id,
                        "employee_id": emp_id,
                        "track_id": track_id,
                        "confidence": 95.0,
                        "description": description,
                        "zone_name": zone_entered,
                        "timestamp": datetime.utcnow()
                    }
                    
                    face_roi = None
                    if face_visible:
                        fx_f, fy_f, fw_f, fh_f = overlapping_face
                        try:
                            face_roi = frame[max(0, fy_f):min(fh, fy_f+fh_f), max(0, fx_f):min(fw, fx_f+fh_f)]
                        except Exception:
                            pass
                            
                    from backend.services.alert_service import AlertService
                    alert = AlertService.process_alert(alert_data, frame=frame, face_roi=face_roi)
                    
                    self.active_intrusions[intrusion_key] = {
                        "alert_id": alert.id,
                        "entry_time": now
                    }
                else:
                    intrusion_info = self.active_intrusions[intrusion_key]
                    elapsed = int(now - intrusion_info["entry_time"])
                    try:
                        alert = Alert.query.get(intrusion_info["alert_id"])
                        if alert:
                            alert.duration = elapsed
                            # Do NOT commit here. Let the periodic commit loop handle it.
                    except Exception as e:
                        print(f"Error updating intrusion duration: {e}")
            
            results.append({
                "track_id": track_id,
                "box": box,
                "zone": zone_entered or zone,
                "uniform_color": torso_color,
                "classification": classification,
                "face_visible": face_visible,
                "face_box": overlapping_face,
                "phone_detected": phone_detected
            })

            # Styled overlays
            is_overtime = False
            if emp_id and emp_id in self.employee_shifts_cache:
                shift_info = self.employee_shifts_cache[emp_id]
                shift_end_str = shift_info.get("shift_end")
                if shift_end_str:
                    try:
                        now_local = datetime.now().time()
                        shift_end_time = datetime.strptime(shift_end_str, "%H:%M").time()
                        if now_local > shift_end_time:
                            is_overtime = True
                    except Exception:
                        pass
                        
            color = (142, 155, 176) # Default Gray
            if phone_detected:
                color = (239, 68, 68) # Red alert if using phone
            elif zone_entered:
                color = (239, 68, 68) # Red if inside custom restricted zone
            elif is_overtime:
                color = (11, 158, 245) # Orange (BGR: (11, 158, 245)) for overtime
            elif classification["employee_id"]:
                color = (16, 185, 129) if classification["category"] == "Employee" else (59, 130, 246)

            # Draw on normal frame
            cv2.rectangle(frame, (bx, by), (bx+bw, by+bh), color, 2)
            
            lbl_name = f"ID:{track_id} | {classification['name']}"
            if is_overtime:
                lbl_name += " [OVERTIME]"
                
            lbl_details = f"{classification['position']} | {classification['category']}"
            if phone_detected:
                lbl_details += " [PHONE]"
                cv2.putText(frame, "PHONE DETECTED", (bx, by + bh + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (239, 68, 68), 1, cv2.LINE_AA)
            elif zone_entered:
                lbl_details += f" | {zone_entered}"
                cv2.putText(frame, "INTRUSION ALERT", (bx, by + bh + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (239, 68, 68), 1, cv2.LINE_AA)
            elif is_overtime:
                cv2.putText(frame, "SHIFT EXCEEDED", (bx, by + bh + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (11, 158, 245), 1, cv2.LINE_AA)
            
            cv2.rectangle(frame, (bx, by - 36), (bx+bw, by), color, -1)
            cv2.putText(frame, lbl_name, (bx + 6, by - 22), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 255, 255), 1)
            cv2.putText(frame, lbl_details, (bx + 6, by - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)

            # Draw on anonymous frame
            cv2.rectangle(frame_anon, (bx, by), (bx+bw, by+bh), color, 2)
            lbl_name_anon = f"ID:{track_id} | Unknown Face"
            lbl_details_anon = "Visitor | Person"
            
            cv2.rectangle(frame_anon, (bx, by - 36), (bx+bw, by), color, -1)
            cv2.putText(frame_anon, lbl_name_anon, (bx + 6, by - 22), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 255, 255), 1)
            cv2.putText(frame_anon, lbl_details_anon, (bx + 6, by - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)

        # Clean up inactive intrusions (person exited zone or track disappeared)
        for key in list(self.active_intrusions.keys()):
            tid, zname = key
            if (tid not in tracked_objects) or (current_track_zones.get(tid) != zname):
                entry_info = self.active_intrusions[key]
                final_duration = int(now - entry_info["entry_time"])
                try:
                    alert = Alert.query.get(entry_info["alert_id"])
                    if alert:
                        alert.duration = final_duration
                except Exception as e:
                    print(f"Error closing intrusion: {e}")
                del self.active_intrusions[key]

        return frame, frame_anon, results

    def detect_phone_near_face(self, frame, face_box):
        # Disabled to prevent false positive phone alerts on CPU/legacy cascades
        return False
