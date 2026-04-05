"""
Simple monitoring dashboard for Greeks Collector
Uses Flask for a lightweight web interface
"""

from flask import Flask, render_template_string, jsonify
from datetime import datetime, timedelta
from sqlalchemy import func, desc

from models import OptionGreeks, CollectionLog, IndexExpiry, get_session

app = Flask(__name__)

DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Greeks Collector Dashboard</title>
    <meta http-equiv="refresh" content="60">
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }
        h1 { color: #333; }
        .card {
            background: white;
            border-radius: 8px;
            padding: 20px;
            margin: 15px 0;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .status-ok { color: #28a745; }
        .status-warn { color: #ffc107; }
        .status-error { color: #dc3545; }
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th, td {
            padding: 10px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        th { background: #f8f9fa; }
        .metric {
            display: inline-block;
            padding: 20px;
            margin: 10px;
            background: #007bff;
            color: white;
            border-radius: 8px;
            min-width: 150px;
            text-align: center;
        }
        .metric-value { font-size: 2em; font-weight: bold; }
        .metric-label { font-size: 0.9em; opacity: 0.9; }
    </style>
</head>
<body>
    <h1>📊 Greeks Collector Dashboard</h1>
    <p>Last updated: {{ now }}</p>
    
    <div class="card">
        <h2>📈 Collection Summary (Last 24 Hours)</h2>
        <div class="metric">
            <div class="metric-value">{{ stats.total_records }}</div>
            <div class="metric-label">Total Records</div>
        </div>
        <div class="metric">
            <div class="metric-value">{{ stats.successful_runs }}</div>
            <div class="metric-label">Successful Runs</div>
        </div>
        <div class="metric">
            <div class="metric-value">{{ stats.failed_runs }}</div>
            <div class="metric-label">Failed Runs</div>
        </div>
        <div class="metric">
            <div class="metric-value">{{ stats.avg_duration_ms }}ms</div>
            <div class="metric-label">Avg Duration</div>
        </div>
    </div>
    
    <div class="card">
        <h2>📅 Tracked Expiries</h2>
        <table>
            <tr>
                <th>Index</th>
                <th>Nearest Expiry</th>
                <th>Days to Expiry</th>
                <th>Last Collection</th>
            </tr>
            {% for expiry in expiries %}
            <tr>
                <td><strong>{{ expiry.index_name }}</strong></td>
                <td>{{ expiry.nearest_expiry }}</td>
                <td>{{ expiry.days_to_expiry }}</td>
                <td>{{ expiry.last_collection or 'N/A' }}</td>
            </tr>
            {% endfor %}
        </table>
    </div>
    
    <div class="card">
        <h2>🔄 Recent Collection Logs</h2>
        <table>
            <tr>
                <th>Timestamp</th>
                <th>Index</th>
                <th>Status</th>
                <th>Records</th>
                <th>Duration</th>
            </tr>
            {% for log in recent_logs %}
            <tr>
                <td>{{ log.timestamp }}</td>
                <td>{{ log.index_name }}</td>
                <td class="status-{{ 'ok' if log.status == 'success' else 'error' }}">
                    {{ log.status }}
                </td>
                <td>{{ log.records_collected }}</td>
                <td>{{ log.duration_ms }}ms</td>
            </tr>
            {% endfor %}
        </table>
    </div>
    
    <div class="card">
        <h2>📊 Latest Greeks Sample (NIFTY)</h2>
        <table>
            <tr>
                <th>Strike</th>
                <th>Type</th>
                <th>LTP</th>
                <th>IV</th>
                <th>Delta</th>
                <th>Gamma</th>
                <th>Theta</th>
                <th>Vega</th>
            </tr>
            {% for greek in sample_greeks %}
            <tr>
                <td>{{ greek.strike_price }}</td>
                <td>{{ greek.option_type }}</td>
                <td>{{ greek.ltp }}</td>
                <td>{{ greek.implied_volatility }}</td>
                <td>{{ greek.delta }}</td>
                <td>{{ greek.gamma }}</td>
                <td>{{ greek.theta }}</td>
                <td>{{ greek.vega }}</td>
            </tr>
            {% endfor %}
        </table>
    </div>
</body>
</html>
"""


@app.route('/')
def dashboard():
    """Main dashboard view"""
    session = get_session()
    now = datetime.now()
    yesterday = now - timedelta(days=1)
    
    try:
        # Get collection stats for last 24 hours
        stats_query = session.query(
            func.sum(CollectionLog.records_collected).label('total_records'),
            func.count(CollectionLog.id).filter(CollectionLog.status == 'success').label('successful'),
            func.count(CollectionLog.id).filter(CollectionLog.status == 'failed').label('failed'),
            func.avg(CollectionLog.duration_ms).label('avg_duration')
        ).filter(CollectionLog.timestamp >= yesterday).first()
        
        stats = {
            'total_records': stats_query.total_records or 0,
            'successful_runs': stats_query.successful or 0,
            'failed_runs': stats_query.failed or 0,
            'avg_duration_ms': round(stats_query.avg_duration or 0, 1)
        }
        
        # Get tracked expiries
        expiries_raw = session.query(IndexExpiry).all()
        expiries = []
        for exp in expiries_raw:
            days_to_expiry = (exp.nearest_expiry - now.date()).days if exp.nearest_expiry else 'N/A'
            
            # Get last collection for this index
            last_log = session.query(CollectionLog).filter(
                CollectionLog.index_name == exp.index_name,
                CollectionLog.status == 'success'
            ).order_by(desc(CollectionLog.timestamp)).first()
            
            expiries.append({
                'index_name': exp.index_name,
                'nearest_expiry': exp.nearest_expiry.strftime('%d %b %Y') if exp.nearest_expiry else 'N/A',
                'days_to_expiry': days_to_expiry,
                'last_collection': last_log.timestamp.strftime('%H:%M:%S') if last_log else None
            })
        
        # Get recent collection logs
        recent_logs = session.query(CollectionLog).order_by(
            desc(CollectionLog.timestamp)
        ).limit(20).all()
        
        logs_formatted = [{
            'timestamp': log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'index_name': log.index_name,
            'status': log.status,
            'records_collected': log.records_collected,
            'duration_ms': log.duration_ms
        } for log in recent_logs]
        
        # Get sample Greeks data
        sample_greeks = session.query(OptionGreeks).filter(
            OptionGreeks.underlying == 'NIFTY'
        ).order_by(desc(OptionGreeks.timestamp)).limit(10).all()
        
        greeks_formatted = [{
            'strike_price': g.strike_price,
            'option_type': g.option_type,
            'ltp': round(g.ltp, 2) if g.ltp else '-',
            'implied_volatility': round(g.implied_volatility, 2) if g.implied_volatility else '-',
            'delta': round(g.delta, 4) if g.delta else '-',
            'gamma': round(g.gamma, 6) if g.gamma else '-',
            'theta': round(g.theta, 4) if g.theta else '-',
            'vega': round(g.vega, 4) if g.vega else '-'
        } for g in sample_greeks]
        
        return render_template_string(
            DASHBOARD_HTML,
            now=now.strftime('%Y-%m-%d %H:%M:%S'),
            stats=stats,
            expiries=expiries,
            recent_logs=logs_formatted,
            sample_greeks=greeks_formatted
        )
        
    finally:
        session.close()


@app.route('/api/stats')
def api_stats():
    """API endpoint for stats"""
    session = get_session()
    now = datetime.now()
    yesterday = now - timedelta(days=1)
    
    try:
        # Get collection stats
        stats = session.query(
            func.sum(CollectionLog.records_collected).label('total_records'),
            func.count(CollectionLog.id).filter(CollectionLog.status == 'success').label('successful'),
            func.count(CollectionLog.id).filter(CollectionLog.status == 'failed').label('failed')
        ).filter(CollectionLog.timestamp >= yesterday).first()
        
        return jsonify({
            'status': 'ok',
            'timestamp': now.isoformat(),
            'stats': {
                'total_records_24h': stats.total_records or 0,
                'successful_runs': stats.successful or 0,
                'failed_runs': stats.failed or 0
            }
        })
    finally:
        session.close()


@app.route('/api/health')
def health_check():
    """Health check endpoint"""
    session = get_session()
    
    try:
        # Check database connectivity
        session.execute("SELECT 1")
        
        # Check last collection time
        last_log = session.query(CollectionLog).order_by(
            desc(CollectionLog.timestamp)
        ).first()
        
        last_collection = None
        if last_log:
            last_collection = last_log.timestamp.isoformat()
        
        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'last_collection': last_collection
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500
    finally:
        session.close()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
