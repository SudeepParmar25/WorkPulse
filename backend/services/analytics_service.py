from datetime import datetime, timedelta, date
from sqlalchemy import func
from backend.database.db import db
from backend.models.models import Employee, Attendance, Alert, CustomerCount

class AnalyticsService:
    @staticmethod
    def get_dashboard_analytics(user_id, range_preset='week', start_date_str=None, end_date_str=None):
        """Compiles real database-driven operational and security statistics."""
        today = date.today()
        
        # 1. Parse date bounds
        if range_preset == 'today':
            start_date = today
            end_date = today
        elif range_preset == 'week':
            start_date = today - timedelta(days=6)
            end_date = today
        elif range_preset == 'month':
            start_date = today - timedelta(days=29)
            end_date = today
        else:
            if start_date_str:
                try:
                    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                except Exception:
                    start_date = today - timedelta(days=6)
            else:
                start_date = today - timedelta(days=6)
            if end_date_str:
                try:
                    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                except Exception:
                    end_date = today
            else:
                end_date = today

        # Aggregate restricted zone intrusion statistics in the date range
        intrusion_alerts = Alert.query.filter(
            Alert.user_id == user_id,
            Alert.type == "restricted_zone_intrusion",
            func.date(Alert.timestamp) >= start_date,
            func.date(Alert.timestamp) <= end_date
        ).order_by(Alert.timestamp.desc()).all()
        
        breaches_by_zone_map = {}
        total_duration = 0
        valid_duration_count = 0
        recent_breaches_list = []
        
        for alert in intrusion_alerts:
            zname = alert.zone_name or "Unknown Zone"
            breaches_by_zone_map[zname] = breaches_by_zone_map.get(zname, 0) + 1
            
            if alert.duration > 0:
                total_duration += alert.duration
                valid_duration_count += 1
                
            emp_name = "Visitor"
            if alert.employee_id:
                emp = Employee.query.get(alert.employee_id)
                if emp:
                    emp_name = emp.name
                    
            recent_breaches_list.append({
                "id": alert.id,
                "zone_name": zname,
                "name": emp_name,
                "timestamp": alert.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "duration": alert.duration,
                "snapshot_path": alert.snapshot_path,
                "face_crop_path": alert.face_crop_path
            })
            
        avg_dur = round(total_duration / valid_duration_count, 1) if valid_duration_count > 0 else 0.0
        breaches_by_zone = [{"zone": z, "count": c} for z, c in breaches_by_zone_map.items()]
        
        restricted_zone_data = {
            "total_breaches": len(intrusion_alerts),
            "average_duration": avg_dur,
            "breaches_by_zone": breaches_by_zone,
            "recent_breaches": recent_breaches_list
        }

        # Fetch employees
        employees = Employee.query.filter_by(user_id=user_id).all()
        emp_ids = [e.id for e in employees]
        emp_map = {e.id: e for e in employees}
        
        # Empty State response if no employees registered
        if not emp_ids:
            return {
                "summary": {"active_employees": 0, "attendance_rate": 0, "avg_productivity": 0, "late_rate": 0},
                "hours_worked": [],
                "productivity_trend": [],
                "late_vs_ontime": {"late": 0, "on_time": 0},
                "active_vs_idle": {"active": 0, "idle": 0},
                "phone_usage": [],
                "department_productivity": [],
                "customer_count": [],
                "alert_trends": [],
                "security_events": 0,
                "recognition_accuracy": [],
                "rankings": {"top": [], "needs_improvement": []},
                "restricted_zones": restricted_zone_data
            }

        # Query attendance records in date range
        records = Attendance.query.filter(
            Attendance.employee_id.in_(emp_ids),
            Attendance.date >= start_date,
            Attendance.date <= end_date
        ).all()
        
        actual_attendances = len(records)
        day_diff = (end_date - start_date).days + 1
        total_possible_days = len(employees) * day_diff
        
        # Attendance & punctuality rates
        attendance_rate = round((actual_attendances / total_possible_days) * 100.0, 1) if total_possible_days > 0 else 0.0
        avg_prod_score = sum(r.score for r in records) / actual_attendances if actual_attendances > 0 else 0.0
        late_count = sum(1 for r in records if r.late)
        late_rate = round((late_count / actual_attendances) * 100.0, 1) if actual_attendances > 0 else 0.0
        
        # Daily charts trends initialization
        daily_hours = {}
        daily_prod = {}
        daily_phone = {}
        daily_customers = {}
        daily_alerts = {}
        daily_accuracy = {}
        
        curr = start_date
        while curr <= end_date:
            d_str = curr.strftime('%Y-%m-%d')
            daily_hours[d_str] = 0.0
            daily_prod[d_str] = []
            daily_phone[d_str] = 0.0
            daily_customers[d_str] = []
            daily_alerts[d_str] = 0
            daily_accuracy[d_str] = []
            curr += timedelta(days=1)
            
        total_active_seconds = 0
        total_idle_seconds = 0
        
        for r in records:
            d_str = r.date.strftime('%Y-%m-%d')
            total_time_hours = (r.active_time + r.idle_time) / 3600.0
            if d_str in daily_hours:
                daily_hours[d_str] += round(total_time_hours, 2)
                daily_prod[d_str].append(r.score)
                daily_phone[d_str] += round(r.phone_time / 60.0, 2)
                
            total_active_seconds += r.active_time
            total_idle_seconds += r.idle_time

        # Query customer counts
        cust_records = CustomerCount.query.filter(
            CustomerCount.user_id == user_id,
            func.date(CustomerCount.timestamp) >= start_date,
            func.date(CustomerCount.timestamp) <= end_date
        ).all()
        for c in cust_records:
            d_str = c.timestamp.strftime('%Y-%m-%d')
            if d_str in daily_customers:
                daily_customers[d_str].append(c.count)

        # Query alerts (events)
        alerts_records = Alert.query.filter(
            Alert.user_id == user_id,
            func.date(Alert.timestamp) >= start_date,
            func.date(Alert.timestamp) <= end_date
        ).all()
        
        security_events_count = 0
        for a in alerts_records:
            d_str = a.timestamp.strftime('%Y-%m-%d')
            if d_str in daily_alerts:
                daily_alerts[d_str] += 1
            if a.severity in ("critical", "emergency"):
                security_events_count += 1
            if d_str in daily_accuracy and a.confidence > 0:
                daily_accuracy[d_str].append(a.confidence)

        # Compile lists
        hours_worked_chart = [{"date": d, "hours": round(h, 2)} for d, h in daily_hours.items()] if records else []
        phone_usage_chart = [{"date": d, "minutes": round(m, 2)} for d, m in daily_phone.items()] if records else []
        alert_trends_chart = [{"date": d, "count": count} for d, count in daily_alerts.items()] if alerts_records else []
        
        customer_chart = []
        if cust_records:
            for d, counts in daily_customers.items():
                avg_c = round(sum(counts) / len(counts), 1) if counts else 0.0
                customer_chart.append({"date": d, "count": avg_c})
                
        prod_chart = []
        if records:
            for d, scores in daily_prod.items():
                avg_s = sum(scores) / len(scores) if scores else 0.0
                prod_chart.append({"date": d, "score": round(avg_s, 1)})
                
        accuracy_chart = []
        if alerts_records:
            for d, confs in daily_accuracy.items():
                avg_acc = round(sum(confs) / len(confs), 1) if confs else 0.0
                accuracy_chart.append({"date": d, "accuracy": avg_acc})

        active_vs_idle = {
            "active": round(total_active_seconds / 3600.0, 2),
            "idle": round(total_idle_seconds / 3600.0, 2)
        }
        
        late_vs_ontime = {
            "late": late_count,
            "on_time": max(0, actual_attendances - late_count)
        }

        # Department breakdown
        dept_scores = {}
        for r in records:
            emp = emp_map.get(r.employee_id)
            if emp:
                dept = emp.department or "Operations"
                if dept not in dept_scores:
                    dept_scores[dept] = []
                dept_scores[dept].append(r.score)
                
        dept_productivity_list = []
        for dept, scores in dept_scores.items():
            avg_dept_score = sum(scores) / len(scores)
            dept_productivity_list.append({
                "department": dept,
                "score": round(avg_dept_score, 1)
            })
        dept_productivity_list.sort(key=lambda x: x["department"])

        # Rankings
        emp_stats = {}
        for r in records:
            if r.employee_id not in emp_stats:
                emp_stats[r.employee_id] = []
            emp_stats[r.employee_id].append(r.score)
            
        rankings_list = []
        for emp_id, scores in emp_stats.items():
            avg_score = sum(scores) / len(scores)
            emp = emp_map.get(emp_id)
            if emp:
                rankings_list.append({
                    "name": emp.name,
                    "position": emp.position,
                    "avg_score": round(avg_score, 1)
                })
        rankings_list.sort(key=lambda x: x["avg_score"], reverse=True)
        
        top_performers = rankings_list[:3]
        needs_improvement = [x for x in reversed(rankings_list) if x["avg_score"] < 80.0][:3]

        return {
            "summary": {
                "active_employees": len(employees),
                "attendance_rate": attendance_rate,
                "avg_productivity": round(avg_prod_score, 1),
                "late_rate": late_rate
            },
            "hours_worked": hours_worked_chart,
            "productivity_trend": prod_chart,
            "late_vs_ontime": late_vs_ontime,
            "active_vs_idle": active_vs_idle,
            "phone_usage": phone_usage_chart,
            "department_productivity": dept_productivity_list,
            "customer_count": customer_chart,
            "alert_trends": alert_trends_chart,
            "security_events": security_events_count,
            "recognition_accuracy": accuracy_chart,
            "rankings": {
                "top": top_performers,
                "needs_improvement": needs_improvement
            },
            "restricted_zones": restricted_zone_data
        }
