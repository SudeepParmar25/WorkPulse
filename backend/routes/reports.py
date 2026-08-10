from flask import Blueprint, request, jsonify, send_file
from flask_login import login_required, current_user
from backend.services.report_service import ReportService

reports_bp = Blueprint('reports', __name__)

@reports_bp.route('/api/reports/summary', methods=['GET'])
@login_required
def get_report_summary():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    scope = request.args.get('scope')
    scope_id = request.args.get('scope_id')
    
    # Delegated to decoupled service
    data = ReportService.gather_report_data(current_user.id, start_date, end_date, scope, scope_id)
    return jsonify(data)

@reports_bp.route('/api/reports/pdf', methods=['GET'])
@login_required
def get_report_pdf():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    scope = request.args.get('scope')
    scope_id = request.args.get('scope_id')
    
    # Generate report buffer via service
    buffer = ReportService.generate_pdf_buffer(
        user_id=current_user.id,
        company_name=current_user.company_name,
        start_date_str=start_date,
        end_date_str=end_date,
        scope=scope,
        scope_id=scope_id
    )
    
    filename = f"WorkPulse_Report_{start_date}_to_{end_date}.pdf"
    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype='application/pdf'
    )
