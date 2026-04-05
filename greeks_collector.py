"""
Greeks Data Collector
Fetches option Greeks every minute and stores in database
"""

import json
import logging
import time
import signal
import sys
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional
import schedule
from threading import Thread, Event

from api_client import get_client, AngelOneClient
from instrument_manager import InstrumentManager
from models import OptionGreeks, CollectionLog, get_session, init_database
from config import (
    INDICES_TO_TRACK, COLLECTION_INTERVAL,
    MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE,
    MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE,
    LOG_LEVEL, LOG_FILE
)

# Setup logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class GreeksCollector:
    """Collects and stores option Greeks data"""
    
    def __init__(self):
        self.client: AngelOneClient = get_client()
        self.instrument_manager = InstrumentManager()
        self.index_expiries: Dict[str, str] = {}
        self.stop_event = Event()
        self.is_running = False
        
    def initialize(self) -> bool:
        """Initialize the collector - login, download instruments, find expiries"""
        logger.info("Initializing Greeks Collector...")
        
        # Initialize database
        try:
            init_database()
            logger.info("Database initialized")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            return False
        
        # Login to API
        if not self.client.login():
            logger.error("Failed to login to Angel One API")
            return False
        
        # Download and store instruments
        count = self.instrument_manager.download_and_store_instruments()
        if count == 0:
            logger.error("Failed to download instruments")
            return False
        
        # Find nearest expiries for all indices
        self.index_expiries = self.instrument_manager.update_index_expiries_in_db()
        if not self.index_expiries:
            logger.error("Failed to find index expiries")
            return False
        
        logger.info(f"Initialized successfully. Tracking expiries: {self.index_expiries}")
        return True
    
    def is_market_hours(self) -> bool:
        """Check if current time is within market hours"""
        now = datetime.now()
        
        # Check if weekday (Monday = 0, Sunday = 6)
        if now.weekday() > 4:  # Saturday or Sunday
            return False
        
        market_open = now.replace(hour=MARKET_OPEN_HOUR, minute=MARKET_OPEN_MINUTE, second=0)
        market_close = now.replace(hour=MARKET_CLOSE_HOUR, minute=MARKET_CLOSE_MINUTE, second=0)
        
        return market_open <= now <= market_close
    
    def collect_greeks_for_index(self, index_name: str, expiry_str: str) -> int:
        """
        Collect Greeks data for a single index
        
        Args:
            index_name: Name of index (e.g., "NIFTY")
            expiry_str: Expiry date string (e.g., "25JAN2024")
        
        Returns:
            Number of records collected
        """
        start_time = time.time()
        session = get_session()
        records_collected = 0
        
        try:
            # Fetch Greeks from API
            greeks_response = self.client.get_option_greeks(index_name, expiry_str)
            
            if not greeks_response:
                raise Exception("Empty response from Greeks API")
            
            # Check for successful response
            if not greeks_response.get('status') and not greeks_response.get('success'):
                error_msg = greeks_response.get('message', 'Unknown error')
                raise Exception(f"API error: {error_msg}")
            
            # Get the data
            greeks_data = greeks_response.get('data', [])
            
            if not greeks_data:
                logger.warning(f"No Greeks data returned for {index_name} {expiry_str}")
                return 0
            
            # Parse expiry date
            try:
                expiry_date = datetime.strptime(expiry_str, '%d%b%Y').date()
            except ValueError:
                expiry_date = date.today()
            
            timestamp = datetime.utcnow()
            
            # Process each strike/option
            for item in greeks_data:
                try:
                    # Handle both CE and PE in the response
                    for option_type in ['CE', 'PE']:
                        option_data = item.get(option_type, {})
                        if not option_data:
                            continue
                        
                        greek = OptionGreeks(
                            timestamp=timestamp,
                            underlying=index_name,
                            expiry_date=expiry_date,
                            strike_price=float(item.get('strikePrice', 0)),
                            option_type=option_type,
                            token=str(option_data.get('token', '')),
                            symbol=str(option_data.get('symbol', '')),
                            delta=self._safe_float(option_data.get('delta')),
                            gamma=self._safe_float(option_data.get('gamma')),
                            theta=self._safe_float(option_data.get('theta')),
                            vega=self._safe_float(option_data.get('vega')),
                            implied_volatility=self._safe_float(option_data.get('iv')),
                            ltp=self._safe_float(option_data.get('ltp')),
                            open_interest=self._safe_int(option_data.get('oi')),
                            volume=self._safe_int(option_data.get('volume')),
                            bid_price=self._safe_float(option_data.get('bidPrice')),
                            ask_price=self._safe_float(option_data.get('askPrice')),
                            raw_response=json.dumps(item) if records_collected < 5 else None
                        )
                        session.add(greek)
                        records_collected += 1
                        
                except Exception as e:
                    logger.debug(f"Error processing item: {e}")
                    continue
            
            # Commit all records
            session.commit()
            
            # Log the collection
            duration_ms = int((time.time() - start_time) * 1000)
            log_entry = CollectionLog(
                index_name=index_name,
                expiry_date=expiry_date,
                status='success',
                records_collected=records_collected,
                duration_ms=duration_ms
            )
            session.add(log_entry)
            session.commit()
            
            logger.info(f"Collected {records_collected} Greeks records for {index_name} in {duration_ms}ms")
            
        except Exception as e:
            session.rollback()
            
            # Log the failure
            try:
                log_entry = CollectionLog(
                    index_name=index_name,
                    expiry_date=date.today(),
                    status='failed',
                    records_collected=0,
                    error_message=str(e),
                    duration_ms=int((time.time() - start_time) * 1000)
                )
                session.add(log_entry)
                session.commit()
            except:
                pass
            
            logger.error(f"Error collecting Greeks for {index_name}: {e}")
            
        finally:
            session.close()
        
        return records_collected
    
    def _safe_float(self, value) -> Optional[float]:
        """Safely convert to float"""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    
    def _safe_int(self, value) -> Optional[int]:
        """Safely convert to int"""
        if value is None:
            return None
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return None
    
    def collect_all_greeks(self):
        """Collect Greeks for all tracked indices"""
        if not self.is_market_hours():
            logger.debug("Outside market hours, skipping collection")
            return
        
        logger.info("Starting Greeks collection cycle...")
        
        total_records = 0
        for index_name, expiry_str in self.index_expiries.items():
            records = self.collect_greeks_for_index(index_name, expiry_str)
            total_records += records
            time.sleep(0.5)  # Small delay between API calls
        
        logger.info(f"Collection cycle complete. Total records: {total_records}")
    
    def refresh_expiries(self):
        """Refresh expiry information - run daily"""
        logger.info("Refreshing expiry information...")
        
        # Re-download instruments
        self.instrument_manager.download_and_store_instruments()
        
        # Update expiries
        self.index_expiries = self.instrument_manager.update_index_expiries_in_db()
        
        logger.info(f"Expiries updated: {self.index_expiries}")
    
    def run_scheduler(self):
        """Run the scheduled collection"""
        logger.info("Starting scheduler...")
        
        # Schedule Greeks collection every minute
        schedule.every(COLLECTION_INTERVAL).seconds.do(self.collect_all_greeks)
        
        # Schedule expiry refresh daily at 8:00 AM
        schedule.every().day.at("08:00").do(self.refresh_expiries)
        
        # Schedule token refresh every 6 hours
        schedule.every(6).hours.do(self.client.refresh_session)
        
        self.is_running = True
        
        while not self.stop_event.is_set():
            schedule.run_pending()
            time.sleep(1)
    
    def start(self):
        """Start the collector in background thread"""
        if self.is_running:
            logger.warning("Collector is already running")
            return
        
        # Initial collection
        self.collect_all_greeks()
        
        # Start scheduler in background
        scheduler_thread = Thread(target=self.run_scheduler, daemon=True)
        scheduler_thread.start()
        
        logger.info("Greeks collector started")
    
    def stop(self):
        """Stop the collector"""
        logger.info("Stopping Greeks collector...")
        self.stop_event.set()
        self.is_running = False
        self.client.logout()
        logger.info("Greeks collector stopped")


def main():
    """Main entry point"""
    collector = GreeksCollector()
    
    # Handle graceful shutdown
    def signal_handler(signum, frame):
        logger.info("Shutdown signal received...")
        collector.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Initialize
    if not collector.initialize():
        logger.error("Failed to initialize collector")
        sys.exit(1)
    
    # Start collection
    logger.info("Starting continuous Greeks collection...")
    logger.info("Press Ctrl+C to stop")
    
    collector.start()
    
    # Keep main thread alive
    try:
        while collector.is_running:
            time.sleep(1)
    except KeyboardInterrupt:
        collector.stop()


if __name__ == "__main__":
    main()
