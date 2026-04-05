"""
Flask Monitoring Dashboard with Download Feature
"""

from flask import Flask, render_template_string, jsonify, Response, request
from datetime import datetime, timedelta, date
from sqlalchemy import func, desc
import csv
import io
from models import OptionGreeks, CollectionLog, IndexExpiry, get_session

app = Flask(__name__)

DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Greeks Collector Dashboard</title>
    <meta http-equiv="refresh" content="60">
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #1a1a2e; color: #eee; }
        h1 { color: #00d4ff; }
        h2 { color: #00d4ff; margin-top: 20px; }
        .card { background: #16213e; padding: 20px; margin: 10px 0; border-radius: 8px; }
        .stat { display: inline-block; margin: 10px 20px; }
        .stat-value { font-size: 2em; color: #00d4ff; }
        .stat-label { color: #888; }
        table { width: 100%; border-collapse: collapse; margin: 10px 0; }
        th, td { padding: 10px; text-align: left; border-bottom: 1px solid #333; }
        th { background: #0f3460; }
        .success { color: #00ff88; }
        .failed { color: #ff4444; }
        .btn { background: #00d4ff; color: #1a1a2e; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; margin: 5px; text-decoration: none; display: inline-block; font-weight: bold; }
        .btn:hover { background: #00a8cc; }
        .btn-danger { background: #ff4444; }
        .download-section { margin: 20px 0; }
        select, input { padding: 8px; margin: 5px; border-radius: 4px; border: 1px solid #333; background: #0f3460; color: #eee; }
        form { display: inline; }
    </style>
</head>
<body>
    <h1>📊 Greeks Collector Dashboard</h1>
    
    <div class="card">
        <h2>Collection Stats (Last 24h)</h2>
        <div class="stat">
            <div class="stat-value">{{ stats.total_records }}</div>
            <div class="stat-label">Records Collected</div>
        </div>
        <div class="stat">
            <div class="stat-value">{{ stats.successful_runs }}</div>
            <div class="stat-label">Successful Runs</div>
        </div>
        <div class="stat">
            <div class="stat-value">{{ stats.failed_runs }}</div>
            <div class="stat-label">Failed Runs</div>
        </div>
        <div class="stat">
            <div class="stat-value">{{ stats.avg_duration }}ms</div>
            <div class="stat-label">Avg Duration</div>
        </div>
        <div class="stat">
            <div class="stat-value">{{ stats.total_all_time }}</div>
            <div class="stat-label">Total Records (All Time)</div>
        </div>
    </div>
    
    <div class="card">
        <h2>📥 Download Data</h2>
        <div class="download-section">
            <h3>Quick Downloads</h3>
            <a href="/download/today" class="btn">Today's Data (CSV)</a>
            <a href="/download/yesterday" class="btn">Yesterday's Data (CSV)</a>
            <a href="/download/week" class="btn">Last 7 Days (CSV)</a>
            <a href="/download/all" class="btn">All Data (CSV)</a>
        </div>
        
        <div class="download-section">
            <h3>Custom Download</h3>
            <form action="/download/custom" method="get">
                <label>Underlying:</label>
                <select name="underlying">
                    <option value="ALL">All</option>
                    <option value="NIFTY">NIFTY</option>
                    <option value="BANKNIFTY">BANKNIFTY</option>
                    <option value="FINNIFTY">FINNIFTY</option>
                    <option value="MIDCPNIFTY">MIDCPNIFTY</option>
                </select>
                <label>From:</label>
                <input type="date" name="from_date" value="{{ today }}">
                <label>To:</label>
                <input type="date" name="to_date" value="{{ today }}">
                <button type="submit" class="btn">Download CSV</button>
            </form>
        </div>
    </div>
    
    <div class="card">
        <h2>Tracked Expiries</h2>
        <table>
            <tr><th>Index</th><th>Nearest Expiry</th><th>Updated</th></tr>
            {% for exp in expiries %}
            <tr>
                <td>{{ exp.index_name }}</td>
                <td>{{ exp.expiry_str }}</td>
                <td>{{ exp.updated_at.strftime('%Y-%m-%d %H:%M') if exp.updated_at else 'N/A' }}</td>
            </tr>
            {% endfor %}
        </table>
    </div>
    
    <div class="card">
        <h2>Recent Collection Logs</h2>
        <table>
            <tr><th>Time</th><th>Status</th><th>Records</th><th>Duration</th></tr>
            {% for log in logs %}
            <tr>
                <td>{{ log.timestamp.strftime('%Y-%m-%d %H:%M:%S') }}</td>
                <td class="{{ log.status }}">{{ log.status }}</td>
                <td>{{ log.records_collected }}</td>
                <td>{{ log.duration_ms }}ms</td>
            </tr>
            {% endfor %}
        </table>
    </div>
    
    <div class="card">
        <h2>Recent Greeks Data (Sample)</h2>
        <table>
            <tr><th>Time</th><th>Underlying</th><th>Strike</th><th>Type</th><th>LTP</th><th>IV</th><th>Delta</th><th>OI</th></tr>
            {% for g in greeks_sample %}
            <tr>
                <td>{{ g.timestamp.strftime('%H:%M:%S') }}</td>
                <td>{{ g.underlying }}</td>
                <td>{{ g.strike_price }}</td>
                <td>{{ g.option_type }}</td>
                <td>{{ "%.2f"|format(g.ltp) if g.ltp else 'N/A' }}</td>
                <td>{{ "%.2f"|format(g.implied_volatility) if g.implied_volatility else 'N/A' }}</td>
                <td>{{ "%.4f"|format(g.delta) if g.delta else 'N/A' }}</td>
                <td>{{ g.open_interest }}</td>
            </tr>
            {% endfor %}
        </table>
    </div>
    
    <p style="color:#666">Last updated: {{ now }} | Auto-refresh: 60s</p>
</body>
</html>
"""

@app.route('/')
def dashboard():
    session = get_session()
    try:
        since = datetime.now() - timedelta(hours=24)
        
        logs = session.query(CollectionLog).filter(
            CollectionLog.timestamp >= since
        ).order_by(desc(CollectionLog.timestamp)).limit(50).all()
        
        successful = len([l for l in logs if l.status == 'success'])
        failed = len([l for l in logs if l.status == 'failed'])
        total_records = sum(l.records_collected or 0 for l in logs)
        avg_duration = sum(l.duration_ms or 0 for l in logs) // len(logs) if logs else 0
        
        total_all_time = session.query(func.count(OptionGreeks.id)).scalar() or 0
        
        expiries = session.query(IndexExpiry).all()
        
        greeks_sample = session.query(OptionGreeks).order_by(desc(OptionGreeks.timestamp)).limit(10).all()
        
        stats = {
            'total_records': total_records,
            'successful_runs': successful,
            'failed_runs': failed,
            'avg_duration': avg_duration,
            'total_all_time': total_all_time
        }
        
        return render_template_string(
            DASHBOARD_HTML,
            stats=stats,
            expiries=expiries,
            logs=logs[:10],
            greeks_sample=greeks_sample,
            now=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            today=date.today().isoformat()
        )
    finally:
        session.close()

def generate_csv(query_results):
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow([
        'timestamp', 'underlying', 'expiry_date', 'strike_price', 
        'option_type', 'symbol', 'ltp', 'implied_volatility',
        'delta', 'gamma', 'theta', 'vega', 'open_interest', 'volume'
    ])
    
    # Data
    for r in query_results:
        writer.writerow([
            r.timestamp.isoformat() if r.timestamp else '',
            r.underlying,
            r.expiry_date.isoformat() if r.expiry_date else '',
            r.strike_price,
            r.option_type,
            r.symbol,
            r.ltp,
            r.implied_volatility,
            r.delta,
            r.gamma,
            r.theta,
            r.vega,
            r.open_interest,
            r.volume
        ])
    
    return output.getvalue()

@app.route('/download/today')
def download_today():
    session = get_session()
    try:
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        records = session.query(OptionGreeks).filter(
            OptionGreeks.timestamp >= today_start
        ).order_by(OptionGreeks.timestamp).all()
        
        csv_data = generate_csv(records)
        filename = f"greeks_today_{date.today().isoformat()}.csv"
        
        return Response(
            csv_data,
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename={filename}'}
        )
    finally:
        session.close()

@app.route('/download/yesterday')
def download_yesterday():
    session = get_session()
    try:
        yesterday = date.today() - timedelta(days=1)
        yesterday_start = datetime.combine(yesterday, datetime.min.time())
        yesterday_end = datetime.combine(yesterday, datetime.max.time())
        
        records = session.query(OptionGreeks).filter(
            OptionGreeks.timestamp >= yesterday_start,
            OptionGreeks.timestamp <= yesterday_end
        ).order_by(OptionGreeks.timestamp).all()
        
        csv_data = generate_csv(records)
        filename = f"greeks_{yesterday.isoformat()}.csv"
        
        return Response(
            csv_data,
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename={filename}'}
        )
    finally:
        session.close()

@app.route('/download/week')
def download_week():
    session = get_session()
    try:
        week_ago = datetime.now() - timedelta(days=7)
        records = session.query(OptionGreeks).filter(
            OptionGreeks.timestamp >= week_ago
        ).order_by(OptionGreeks.timestamp).all()
        
        csv_data = generate_csv(records)
        filename = f"greeks_last_7_days_{date.today().isoformat()}.csv"
        
        return Response(
            csv_data,
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename={filename}'}
        )
    finally:
        session.close()

@app.route('/download/all')
def download_all():
    session = get_session()
    try:
        records = session.query(OptionGreeks).order_by(OptionGreeks.timestamp).all()
        
        csv_data = generate_csv(records)
        filename = f"greeks_all_data_{date.today().isoformat()}.csv"
        
        return Response(
            csv_data,
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename={filename}'}
        )
    finally:
        session.close()

@app.route('/download/custom')
def download_custom():
    session = get_session()
    try:
        underlying = request.args.get('underlying', 'ALL')
        from_date = request.args.get('from_date', date.today().isoformat())
        to_date = request.args.get('to_date', date.today().isoformat())
        
        from_dt = datetime.fromisoformat(from_date)
        to_dt = datetime.fromisoformat(to_date).replace(hour=23, minute=59, second=59)
        
        query = session.query(OptionGreeks).filter(
            OptionGreeks.timestamp >= from_dt,
            OptionGreeks.timestamp <= to_dt
        )
        
        if underlying != 'ALL':
            query = query.filter(OptionGreeks.underlying == underlying)
        
        records = query.order_by(OptionGreeks.timestamp).all()
        
        csv_data = generate_csv(records)
        filename = f"greeks_{underlying}_{from_date}_to_{to_date}.csv"
        
        return Response(
            csv_data,
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename={filename}'}
        )
    finally:
        session.close()

@app.route('/api/health')
def health():
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()})

@app.route('/api/stats')
def api_stats():
    session = get_session()
    try:
        since = datetime.now() - timedelta(hours=24)
        total_24h = session.query(func.count(OptionGreeks.id)).filter(
            OptionGreeks.timestamp >= since
        ).scalar()
        total_all = session.query(func.count(OptionGreeks.id)).scalar()
        return jsonify({
            'records_24h': total_24h,
            'records_all_time': total_all,
            'timestamp': datetime.now().isoformat()
        })
    finally:
        session.close()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
