import time
from datetime import datetime, date, timedelta
from backend.database.db import db
from backend.models.models import User, Employee, Attendance, Alert

class AttendanceService:
    @staticmethod
    def check_in_employee(user_id, employee_id):
        """Checks in an employee, calculating if they are late according to work rules."""
        today = date.today()
        att = Attendance.query.filter_by(employee_id=employee_id, date=today).first()
        emp = Employee.query.get(employee_id)
        if not emp:
            return None
            
        check_in_time = datetime.now()
        admin = User.query.get(user_id)
        
        # Calculate late threshold
        start_str = admin.work_hours_start or '09:00'
        is_late = False
        try:
            h, m = map(int, start_str.split(':'))
            late_limit = check_in_time.replace(hour=h, minute=m, second=0, microsecond=0) + timedelta(minutes=admin.late_threshold)
            is_late = check_in_time > late_limit
        except Exception:
            is_late = check_in_time.hour >= 9

        if not att:
            # First check-in of the day
            att = Attendance(
                employee_id=employee_id,
                date=today,
                check_in=check_in_time,
                late=is_late
            )
            db.session.add(att)
            
            # Log checkin alert via session
            alert = Alert(
                user_id=user_id,
                employee_id=employee_id,
                type="employee_check_in",
                severity="warning" if is_late else "success",
                camera="Main Entrance",
                confidence=100.0,
                description=f"Punctuality: {emp.name} checked in {'LATE' if is_late else 'on-time'} at {check_in_time.strftime('%H:%M:%S')}",
                timestamp=datetime.utcnow()
            )
            db.session.add(alert)
        else:
            # Re-checkin (resume shift session)
            att.check_out = None
            
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Attendance check-in db error: {e}")
            
        return att

    @staticmethod
    def check_out_employee(user_id, employee_id, last_seen_time):
        """Processes shift checkout, updating scores and logging exit alerts."""
        today = date.today()
        att = Attendance.query.filter_by(employee_id=employee_id, date=today).first()
        emp = Employee.query.get(employee_id)
        if not att or not emp:
            return None
            
        checkout_time = datetime.fromtimestamp(last_seen_time)
        att.check_out = checkout_time
        att.calculate_score()
        
        alert = Alert(
            user_id=user_id,
            employee_id=employee_id,
            type="employee_checkout",
            severity="info",
            camera="Main Entrance",
            confidence=100.0,
            description=f"Punctuality: {emp.name} checked out at {checkout_time.strftime('%H:%M:%S')}. Score: {att.score}%",
            timestamp=datetime.utcnow()
        )
        db.session.add(alert)
        
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Attendance check-out db error: {e}")
            
        return att

    @staticmethod
    def accumulate_time(employee_id, active_delta=0.0, idle_delta=0.0, phone_delta=0.0):
        """Accumulates working/idle/phone hours on the active attendance sheet."""
        today = date.today()
        att = Attendance.query.filter_by(employee_id=employee_id, date=today).first()
        if att:
            if active_delta > 0:
                att.active_time += int(active_delta)
            if idle_delta > 0:
                att.idle_time += int(idle_delta)
            if phone_delta > 0:
                att.phone_time += int(phone_delta)
            att.calculate_score()
            # Do not commit immediately, let the caller trigger database commits periodically
            return True
        return False
