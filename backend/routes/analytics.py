from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from backend.services.analytics_service import AnalyticsService

analytics_bp = Blueprint('analytics', __name__)

@analytics_bp.route('/api/analytics/dashboard', methods=['GET'])
@login_required
def get_dashboard_analytics():
    range_preset = request.args.get('range', 'week')
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    
    # Call decoupled service
    data = AnalyticsService.get_dashboard_analytics(
        user_id=current_user.id,
        range_preset=range_preset,
        start_date_str=start_date_str,
        end_date_str=end_date_str
    )
    
    return jsonify(data)
