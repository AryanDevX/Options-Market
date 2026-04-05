"""
Data Export Utilities
Export Greeks data to CSV, analyze trends, and generate reports
"""

import csv
import json
import os
from datetime import datetime, date, timedelta
from typing import Optional, List
import pandas as pd
from sqlalchemy import func, desc

from models import OptionGreeks, CollectionLog, Instrument, IndexExpiry, get_session


def export_greeks_to_csv(
    underlying: str,
    start_date: date,
    end_date: date,
    output_file: str
) -> int:
    """
    Export Greeks data for a specific underlying to CSV
    
    Args:
        underlying: Index/stock name (e.g., "NIFTY")
        start_date: Start date for export
        end_date: End date for export
        output_file: Output CSV file path
    
    Returns:
        Number of records exported
    """
    session = get_session()
    
    try:
        query = session.query(OptionGreeks).filter(
            OptionGreeks.underlying == underlying,
            func.date(OptionGreeks.timestamp) >= start_date,
            func.date(OptionGreeks.timestamp) <= end_date
        ).order_by(OptionGreeks.timestamp)
        
        records = query.all()
        
        if not records:
            print(f"No records found for {underlying} between {start_date} and {end_date}")
            return 0
        
        # Write to CSV
        with open(output_file, 'w', newline='') as f:
            writer = csv.writer(f)
            
            # Header
            writer.writerow([
                'timestamp', 'underlying', 'expiry_date', 'strike_price', 
                'option_type', 'symbol', 'ltp', 'implied_volatility',
                'delta', 'gamma', 'theta', 'vega', 'open_interest', 'volume'
            ])
            
            # Data
            for r in records:
                writer.writerow([
                    r.timestamp.isoformat(),
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
        
        print(f"Exported {len(records)} records to {output_file}")
        return len(records)
        
    finally:
        session.close()


def get_iv_history(
    underlying: str,
    strike: float,
    option_type: str,
    days: int = 30
) -> pd.DataFrame:
    """
    Get IV history for a specific option contract
    
    Args:
        underlying: Index name
        strike: Strike price
        option_type: CE or PE
        days: Number of days of history
    
    Returns:
        DataFrame with IV history
    """
    session = get_session()
    start_date = datetime.now() - timedelta(days=days)
    
    try:
        records = session.query(
            OptionGreeks.timestamp,
            OptionGreeks.implied_volatility,
            OptionGreeks.ltp,
            OptionGreeks.delta,
            OptionGreeks.open_interest
        ).filter(
            OptionGreeks.underlying == underlying,
            OptionGreeks.strike_price == strike,
            OptionGreeks.option_type == option_type,
            OptionGreeks.timestamp >= start_date
        ).order_by(OptionGreeks.timestamp).all()
        
        df = pd.DataFrame(records, columns=[
            'timestamp', 'iv', 'ltp', 'delta', 'oi'
        ])
        
        return df
        
    finally:
        session.close()


def get_oi_change_report(
    underlying: str,
    expiry_date: date
) -> pd.DataFrame:
    """
    Get OI change report for all strikes
    
    Args:
        underlying: Index name
        expiry_date: Expiry date
    
    Returns:
        DataFrame with OI changes
    """
    session = get_session()
    
    try:
        # Get today's latest data
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        subquery = session.query(
            OptionGreeks.strike_price,
            OptionGreeks.option_type,
            func.first_value(OptionGreeks.open_interest).over(
                partition_by=[OptionGreeks.strike_price, OptionGreeks.option_type],
                order_by=OptionGreeks.timestamp
            ).label('start_oi'),
            func.last_value(OptionGreeks.open_interest).over(
                partition_by=[OptionGreeks.strike_price, OptionGreeks.option_type],
                order_by=OptionGreeks.timestamp
            ).label('end_oi')
        ).filter(
            OptionGreeks.underlying == underlying,
            OptionGreeks.expiry_date == expiry_date,
            OptionGreeks.timestamp >= today_start
        ).distinct().subquery()
        
        records = session.query(subquery).all()
        
        df = pd.DataFrame(records, columns=['strike', 'type', 'start_oi', 'end_oi'])
        df['oi_change'] = df['end_oi'] - df['start_oi']
        df['oi_change_pct'] = (df['oi_change'] / df['start_oi'] * 100).round(2)
        
        return df
        
    finally:
        session.close()


def generate_daily_summary(target_date: Optional[date] = None) -> dict:
    """
    Generate daily collection summary
    
    Args:
        target_date: Date to summarize (default: today)
    
    Returns:
        Summary dictionary
    """
    if target_date is None:
        target_date = date.today()
    
    session = get_session()
    
    try:
        # Collection stats
        logs = session.query(CollectionLog).filter(
            func.date(CollectionLog.timestamp) == target_date
        ).all()
        
        successful = len([l for l in logs if l.status == 'success'])
        failed = len([l for l in logs if l.status == 'failed'])
        total_records = sum(l.records_collected for l in logs)
        avg_duration = sum(l.duration_ms or 0 for l in logs) / len(logs) if logs else 0
        
        # Records by underlying
        records_by_underlying = session.query(
            OptionGreeks.underlying,
            func.count(OptionGreeks.id)
        ).filter(
            func.date(OptionGreeks.timestamp) == target_date
        ).group_by(OptionGreeks.underlying).all()
        
        # First and last collection times
        first_collection = min((l.timestamp for l in logs), default=None)
        last_collection = max((l.timestamp for l in logs), default=None)
        
        summary = {
            'date': target_date.isoformat(),
            'total_collection_runs': len(logs),
            'successful_runs': successful,
            'failed_runs': failed,
            'success_rate': round(successful / len(logs) * 100, 2) if logs else 0,
            'total_records_collected': total_records,
            'avg_duration_ms': round(avg_duration, 2),
            'first_collection': first_collection.isoformat() if first_collection else None,
            'last_collection': last_collection.isoformat() if last_collection else None,
            'records_by_underlying': dict(records_by_underlying)
        }
        
        return summary
        
    finally:
        session.close()


def cleanup_old_data(days_to_keep: int = 30) -> int:
    """
    Delete old Greeks data to manage storage
    
    Args:
        days_to_keep: Number of days of data to retain
    
    Returns:
        Number of records deleted
    """
    session = get_session()
    cutoff_date = datetime.now() - timedelta(days=days_to_keep)
    
    try:
        # Delete old Greeks data
        deleted = session.query(OptionGreeks).filter(
            OptionGreeks.timestamp < cutoff_date
        ).delete()
        
        # Delete old collection logs
        session.query(CollectionLog).filter(
            CollectionLog.timestamp < cutoff_date
        ).delete()
        
        session.commit()
        print(f"Deleted {deleted} records older than {days_to_keep} days")
        return deleted
        
    except Exception as e:
        session.rollback()
        print(f"Error during cleanup: {e}")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Greeks Data Export Utilities')
    parser.add_argument('command', choices=['export', 'summary', 'cleanup'])
    parser.add_argument('--underlying', default='NIFTY', help='Underlying name')
    parser.add_argument('--days', type=int, default=7, help='Number of days')
    parser.add_argument('--output', default='greeks_export.csv', help='Output file')
    
    args = parser.parse_args()
    
    if args.command == 'export':
        end_date = date.today()
        start_date = end_date - timedelta(days=args.days)
        export_greeks_to_csv(args.underlying, start_date, end_date, args.output)
    
    elif args.command == 'summary':
        summary = generate_daily_summary()
        print(json.dumps(summary, indent=2))
    
    elif args.command == 'cleanup':
        cleanup_old_data(args.days)
