import io
from datetime import datetime, date, timedelta
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from backend.models.models import Employee, Attendance, Alert

class ReportService:
    @staticmethod
    def gather_report_data(user_id, start_date_str=None, end_date_str=None, scope=None, scope_id=None):
        """Compiles real report stats and generates corresponding text advice insights."""
        today = date.today()
        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            except Exception:
                start_date = today - timedelta(days=30)
        else:
            start_date = today - timedelta(days=30)
            
        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            except Exception:
                end_date = today
        else:
            end_date = today
            
        # Query specific alert counts for accurate reporting
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())
        
        target_emp_ids = None
        scope_label = "All Employees"
        
        if scope == "employee" and scope_id:
            try:
                target_emp_ids = [int(scope_id)]
                emp_obj = Employee.query.get(scope_id)
                if emp_obj:
                    scope_label = f"Employee: {emp_obj.name}"
            except Exception:
                pass
        elif scope == "department" and scope_id:
            employees = Employee.query.filter_by(user_id=user_id, department=scope_id).all()
            target_emp_ids = [e.id for e in employees]
            scope_label = f"Department Group: {scope_id}"
            
        phone_q = Alert.query.filter(
            Alert.user_id == user_id,
            Alert.type == "phone_usage",
            Alert.timestamp >= start_dt,
            Alert.timestamp <= end_dt
        )
        if target_emp_ids is not None:
            phone_q = phone_q.filter(Alert.employee_id.in_(target_emp_ids))
        phone_alerts_count = phone_q.count()
        
        zone_q = Alert.query.filter(
            Alert.user_id == user_id,
            Alert.type == "restricted_zone_intrusion",
            Alert.timestamp >= start_dt,
            Alert.timestamp <= end_dt
        )
        if target_emp_ids is not None:
            zone_q = zone_q.filter(Alert.employee_id.in_(target_emp_ids))
        zone_breaches_count = zone_q.count()
        
        # Query Attendance records
        att_q = Attendance.query.join(Employee).filter(
            Employee.user_id == user_id,
            Attendance.date >= start_date,
            Attendance.date <= end_date
        )
        if target_emp_ids is not None:
            att_q = att_q.filter(Attendance.employee_id.in_(target_emp_ids))
            
        records = att_q.all()
        
        if target_emp_ids is not None:
            active_count = len(target_emp_ids)
        else:
            active_count = Employee.query.filter_by(user_id=user_id).count()
            
        total_days = (end_date - start_date).days + 1
        security_count = phone_alerts_count + zone_breaches_count
        
        summary = ""
        analysis = ""
        recommendations = []
        
        if active_count > 0:
            # attendance rate = (total actual records) / (active_count * total_days) * 100
            attendance_rate = round((len(records) / max(1, active_count * total_days)) * 100.0, 1)
            attendance_rate = min(100.0, attendance_rate)
            
            # avg prod score
            prod_scores = [r.score for r in records if r.score is not None]
            avg_prod = round(sum(prod_scores) / len(prod_scores), 1) if prod_scores else 100.0
            
            # late rate
            late_checks = 0
            for r in records:
                if r.check_in:
                    emp_start = r.employee.shift_start or "09:00"
                    try:
                        check_in_time = r.check_in.time()
                        shift_start_time = datetime.strptime(emp_start, "%H:%M").time()
                        if check_in_time > shift_start_time:
                            late_checks += 1
                    except Exception:
                        pass
            late_rate = round((late_checks / len(records)) * 100.0, 1) if records else 0.0
            
            summary = (
                f"Executive surveillance intelligence report for the evaluation period of {start_date} to {end_date} under scope '{scope_label}'. "
                f"For this scope ({active_count} target staff), the average attendance rate was calculated at {attendance_rate}%. "
                f"Punctuality compliance was measured at {round(100 - late_rate, 1)}%, with late arrivals accounting for {late_rate}% of registered shifts. "
                f"The target productivity coefficient averaged {avg_prod}%. "
                f"WorkPulse sensors registered {security_count} total incidents for this scope, consisting of {phone_alerts_count} mobile phone usage alerts during shift hours "
                f"and {zone_breaches_count} restricted zone intrusions."
            )
            
            # Detailed Behavioral analysis
            prod_detail = ""
            if avg_prod >= 85.0:
                prod_detail = "Staff engagement remains exceptional. The target scope shows high compliance with operational guidelines and minimal idle/distraction gaps."
            elif avg_prod >= 70.0:
                prod_detail = "Moderate workforce activity detected. Small pockets of idle time or phone distractions are present during active hours."
            else:
                prod_detail = "Low productivity coefficients flagged. Significant idle time clusters indicate potential understaffing or distraction issues."
                
            security_detail = ""
            if zone_breaches_count > 0:
                security_detail = f"Security boundaries were breached {zone_breaches_count} times by target personnel inside marked restricted zones."
            else:
                security_detail = "Zone integrity is fully intact. Zero unauthorized restricted zone intrusions were detected during this interval."
                
            phone_detail = ""
            if phone_alerts_count > 0:
                phone_detail = f"Operational discipline warnings: {phone_alerts_count} incidents of active mobile phone usage were flagged during shift hours."
            else:
                phone_detail = "No shift-hour cell phone usage policies were breached."
                
            analysis = f"{prod_detail} {security_detail} {phone_detail}"
            
            if late_rate >= 15.0:
                recommendations.append(f"Adjust scheduling policy: Late arrivals stand at {late_rate}%. Consider shifting start thresholds or review shift timing compliance.")
            else:
                recommendations.append("Attendance compliance meets benchmark targets. Maintain current shift templates.")
                
            if phone_alerts_count > 0:
                recommendations.append(f"Minimize distractions: {phone_alerts_count} mobile phone violations were recorded during active shifts. Re-enforce device policies.")
                
            if zone_breaches_count > 0:
                recommendations.append(f"Strengthen restricted access: {zone_breaches_count} restricted area breaches occurred. Review boundary layouts and access logs.")
            else:
                recommendations.append("Restricted zones remain secure. Continue auditing coordinates weekly to confirm coverage.")
        else:
            attendance_rate = 0.0
            avg_prod = 0.0
            late_rate = 0.0
            summary = "No database metrics logged for this scope. Register staff and start surveillance to generate analysis report."
            analysis = "Analysis is not available. Please verify system is online."
            recommendations.append("Register employees to start attendance metrics compilation.")
            recommendations.append("Configure opening/closing settings parameters.")

        return {
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
            "employees_count": active_count,
            "attendance_rate": attendance_rate,
            "avg_productivity": avg_prod,
            "late_rate": late_rate,
            "security_events": security_count,
            "phone_events": phone_alerts_count,
            "zone_breaches": zone_breaches_count,
            "summary": summary,
            "analysis": analysis,
            "recommendations": recommendations
        }

    @staticmethod
    def generate_pdf_buffer(user_id, company_name, start_date_str=None, end_date_str=None, scope=None, scope_id=None):
        """Renders the executive report PDF and returns its BytesIO memory buffer."""
        data = ReportService.gather_report_data(user_id, start_date_str, end_date_str, scope, scope_id)
        
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=letter,
            rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40
        )
        
        styles = getSampleStyleSheet()
        
        title_style = ParagraphStyle(
            'DocTitle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=20,
            textColor=colors.HexColor('#6366f1'), spaceAfter=15
        )
        h2_style = ParagraphStyle(
            'SectionHeader', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=14,
            textColor=colors.HexColor('#1f2937'), spaceBefore=15, spaceAfter=8, keepWithNext=True
        )
        body_style = ParagraphStyle(
            'BodyTextCustom', parent=styles['BodyText'], fontName='Helvetica', fontSize=10,
            leading=14, textColor=colors.HexColor('#374151')
        )
        bullet_style = ParagraphStyle(
            'BulletCustom', parent=body_style, leftIndent=15, firstLineIndent=-10, spaceAfter=5
        )
        
        scope_name = "All Employees"
        if scope == "employee" and scope_id:
            emp = Employee.query.get(scope_id)
            scope_name = f"Employee: {emp.name if emp else 'Unknown'}"
        elif scope == "department" and scope_id:
            scope_name = f"Department Group: {scope_id}"
            
        story = []
        story.append(Paragraph("WorkPulse AI - Executive Performance Report", title_style))
        story.append(Paragraph(f"<b>Company:</b> {company_name or 'Not specified'}", body_style))
        story.append(Paragraph(f"<b>Report Scope:</b> {scope_name}", body_style))
        story.append(Paragraph(f"<b>Date Range:</b> {data['start_date']} to {data['end_date']}", body_style))
        story.append(Paragraph(f"<b>Generated On:</b> {datetime.now().strftime('%Y-%m-%d %H:%M')}", body_style))
        story.append(Spacer(1, 15))
        
        # Metrics Table
        story.append(Paragraph("Key Performance Metrics", h2_style))
        table_data = [
            ["Metric", "Value", "Context"],
            ["Target Personnel Count", str(data["employees_count"]), "Included in chosen scope"],
            ["Attendance Rate", f"{data['attendance_rate']}%", "Average turnup in period"],
            ["Average Productivity Score", f"{data['avg_productivity']}%", "Active ratio during shifts"],
            ["Late Arrival Rate", f"{data['late_rate']}%", "Punctuality index"],
            ["Mobile Phone Incidents", str(data["phone_events"]), "Shift hour usage flags"],
            ["Restricted Zone Breaches", str(data["zone_breaches"]), "Unauthorized area intrusions"],
        ]
        
        t = Table(table_data, colWidths=[200, 100, 220])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#6366f1')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('BOTTOMPADDING', (0,0), (-1,0), 8),
            ('TOPPADDING', (0,0), (-1,0), 8),
            ('BACKGROUND', (0,1), (-1,-1), colors.HexColor('#f9fafb')),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e5e7eb')),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 10),
            ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
            ('FONTSIZE', (0,1), (-1,-1), 9),
            ('BOTTOMPADDING', (0,1), (-1,-1), 6),
            ('TOPPADDING', (0,1), (-1,-1), 6),
        ]))
        
        story.append(t)
        story.append(Spacer(1, 15))
        
        story.append(Paragraph("AI Executive Summary", h2_style))
        story.append(Paragraph(data["summary"], body_style))
        story.append(Spacer(1, 10))
        
        story.append(Paragraph("Behavioral & Productivity Analysis", h2_style))
        story.append(Paragraph(data["analysis"], body_style))
        story.append(Spacer(1, 10))
        
        story.append(Paragraph("Recommended Action Items", h2_style))
        for rec in data["recommendations"]:
            story.append(Paragraph(f"&bull; {rec}", bullet_style))
            
        doc.build(story)
        buffer.seek(0)
        return buffer
