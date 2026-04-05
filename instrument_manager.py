"""
Instrument Manager
Handles downloading, parsing, and storing instrument data
Finds nearest expiry for indices
"""

import json
import logging
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd
from sqlalchemy.orm import Session

from api_client import get_client
from models import Instrument, IndexExpiry, get_session
from config import INDICES_TO_TRACK

logger = logging.getLogger(__name__)


class InstrumentManager:
    """Manages instrument data and expiry calculations"""
    
    def __init__(self):
        self.client = get_client()
        self.instruments_df: Optional[pd.DataFrame] = None
    
    def download_and_store_instruments(self) -> int:
        """
        Download all instruments and store in database
        Returns count of instruments stored
        """
        logger.info("Downloading instrument master...")
        
        instruments = self.client.download_instruments()
        
        if not instruments:
            logger.error("Failed to download instruments")
            return 0
        
        # Convert to DataFrame for easier processing
        self.instruments_df = pd.DataFrame(instruments)
        
        # Parse expiry dates
        self.instruments_df['expiry_parsed'] = pd.to_datetime(
            self.instruments_df['expiry'], 
            format='%d%b%Y',
            errors='coerce'
        )
        
        # Store in database
        session = get_session()
        try:
            # Clear existing instruments (fresh download)
            session.query(Instrument).delete()
            
            count = 0
            batch_size = 5000
            batch = []
            
            for _, row in self.instruments_df.iterrows():
                expiry_date = None
                if pd.notna(row.get('expiry_parsed')):
                    expiry_date = row['expiry_parsed'].date()
                
                instrument = Instrument(
                    token=str(row.get('token', '')),
                    symbol=str(row.get('symbol', '')),
                    name=str(row.get('name', '')),
                    expiry=expiry_date,
                    strike=float(row['strike']) if pd.notna(row.get('strike')) else None,
                    lotsize=int(row['lotsize']) if pd.notna(row.get('lotsize')) else None,
                    instrumenttype=str(row.get('instrumenttype', '')),
                    exch_seg=str(row.get('exch_seg', '')),
                    tick_size=float(row['tick_size']) if pd.notna(row.get('tick_size')) else None
                )
                batch.append(instrument)
                
                if len(batch) >= batch_size:
                    session.bulk_save_objects(batch)
                    session.commit()
                    count += len(batch)
                    batch = []
                    logger.info(f"Stored {count} instruments...")
            
            # Store remaining
            if batch:
                session.bulk_save_objects(batch)
                session.commit()
                count += len(batch)
            
            logger.info(f"Successfully stored {count} instruments")
            return count
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error storing instruments: {str(e)}")
            return 0
        finally:
            session.close()
    
    def find_nearest_expiry(self, index_name: str) -> Optional[Tuple[date, str]]:
        """
        Find the nearest expiry for a given index
        
        Args:
            index_name: Name of index (NIFTY, BANKNIFTY, etc.)
        
        Returns:
            Tuple of (expiry_date, formatted_expiry_string) or None
        """
        if self.instruments_df is None:
            instruments = self.client.download_instruments()
            if instruments:
                self.instruments_df = pd.DataFrame(instruments)
                self.instruments_df['expiry_parsed'] = pd.to_datetime(
                    self.instruments_df['expiry'], 
                    format='%d%b%Y',
                    errors='coerce'
                )
        
        if self.instruments_df is None:
            return None
        
        # Filter for index options (NFO segment, OPTIDX instrument type)
        options_df = self.instruments_df[
            (self.instruments_df['name'] == index_name) &
            (self.instruments_df['exch_seg'] == 'NFO') &
            (self.instruments_df['instrumenttype'] == 'OPTIDX')
        ].copy()
        
        if options_df.empty:
            logger.warning(f"No options found for {index_name}")
            return None
        
        # Get today's date
        today = datetime.now().date()
        
        # Filter for future expiries
        future_expiries = options_df[
            options_df['expiry_parsed'].dt.date >= today
        ]['expiry_parsed'].dropna().unique()
        
        if len(future_expiries) == 0:
            logger.warning(f"No future expiries found for {index_name}")
            return None
        
        # Find nearest expiry
        future_expiries = sorted(future_expiries)
        nearest_expiry = pd.Timestamp(future_expiries[0]).date()
        
        # Format for API call (e.g., "25JAN2024")
        expiry_str = nearest_expiry.strftime('%d%b%Y').upper()
        
        logger.info(f"Nearest expiry for {index_name}: {expiry_str}")
        return nearest_expiry, expiry_str
    
    def get_all_expiries_for_index(self, index_name: str, num_expiries: int = 5) -> List[Tuple[date, str]]:
        """
        Get multiple upcoming expiries for an index
        
        Args:
            index_name: Name of index
            num_expiries: Number of upcoming expiries to return
        
        Returns:
            List of (expiry_date, formatted_string) tuples
        """
        if self.instruments_df is None:
            instruments = self.client.download_instruments()
            if instruments:
                self.instruments_df = pd.DataFrame(instruments)
                self.instruments_df['expiry_parsed'] = pd.to_datetime(
                    self.instruments_df['expiry'], 
                    format='%d%b%Y',
                    errors='coerce'
                )
        
        if self.instruments_df is None:
            return []
        
        # Filter for index options
        options_df = self.instruments_df[
            (self.instruments_df['name'] == index_name) &
            (self.instruments_df['exch_seg'] == 'NFO') &
            (self.instruments_df['instrumenttype'] == 'OPTIDX')
        ].copy()
        
        if options_df.empty:
            return []
        
        today = datetime.now().date()
        
        # Get unique future expiries
        future_expiries = options_df[
            options_df['expiry_parsed'].dt.date >= today
        ]['expiry_parsed'].dropna().unique()
        
        future_expiries = sorted(future_expiries)[:num_expiries]
        
        result = []
        for exp in future_expiries:
            exp_date = pd.Timestamp(exp).date()
            exp_str = exp_date.strftime('%d%b%Y').upper()
            result.append((exp_date, exp_str))
        
        return result
    
    def update_index_expiries_in_db(self) -> Dict[str, str]:
        """
        Update nearest expiries for all tracked indices in database
        Returns dict of index_name -> expiry_string
        """
        session = get_session()
        result = {}
        
        try:
            for index_name in INDICES_TO_TRACK:
                expiry_data = self.find_nearest_expiry(index_name)
                
                if expiry_data:
                    expiry_date, expiry_str = expiry_data
                    
                    # Check if record exists
                    existing = session.query(IndexExpiry).filter(
                        IndexExpiry.index_name == index_name
                    ).first()
                    
                    if existing:
                        existing.nearest_expiry = expiry_date
                        existing.updated_at = datetime.utcnow()
                    else:
                        new_expiry = IndexExpiry(
                            index_name=index_name,
                            nearest_expiry=expiry_date,
                            expiry_type='weekly' if index_name in ['NIFTY', 'BANKNIFTY', 'FINNIFTY'] else 'monthly'
                        )
                        session.add(new_expiry)
                    
                    result[index_name] = expiry_str
                    logger.info(f"{index_name}: Nearest expiry = {expiry_str}")
            
            session.commit()
            return result
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error updating expiries: {str(e)}")
            return {}
        finally:
            session.close()
    
    def get_option_tokens_for_expiry(
        self, 
        index_name: str, 
        expiry_date: date,
        strike_range: int = 20
    ) -> pd.DataFrame:
        """
        Get option tokens for strikes around ATM
        
        Args:
            index_name: Name of index
            expiry_date: Expiry date
            strike_range: Number of strikes above and below ATM
        
        Returns:
            DataFrame with option details
        """
        if self.instruments_df is None:
            return pd.DataFrame()
        
        expiry_str = expiry_date.strftime('%d%b%Y').upper()
        
        # Filter options for this index and expiry
        options = self.instruments_df[
            (self.instruments_df['name'] == index_name) &
            (self.instruments_df['exch_seg'] == 'NFO') &
            (self.instruments_df['instrumenttype'] == 'OPTIDX') &
            (self.instruments_df['expiry'] == expiry_str)
        ].copy()
        
        return options
    
    def get_summary(self) -> Dict:
        """Get summary of loaded instruments"""
        if self.instruments_df is None:
            return {"status": "No data loaded"}
        
        summary = {
            "total_instruments": len(self.instruments_df),
            "exchanges": self.instruments_df['exch_seg'].value_counts().to_dict(),
            "instrument_types": self.instruments_df['instrumenttype'].value_counts().to_dict(),
            "index_options": {}
        }
        
        for index_name in INDICES_TO_TRACK:
            count = len(self.instruments_df[
                (self.instruments_df['name'] == index_name) &
                (self.instruments_df['instrumenttype'] == 'OPTIDX')
            ])
            if count > 0:
                summary["index_options"][index_name] = count
        
        return summary


if __name__ == "__main__":
    # Test the instrument manager
    logging.basicConfig(level=logging.INFO)
    
    manager = InstrumentManager()
    
    # Download instruments
    count = manager.download_and_store_instruments()
    print(f"Stored {count} instruments")
    
    # Find expiries
    expiries = manager.update_index_expiries_in_db()
    print(f"Expiries: {expiries}")
    
    # Print summary
    summary = manager.get_summary()
    print(f"Summary: {json.dumps(summary, indent=2)}")
