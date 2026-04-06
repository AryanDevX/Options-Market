"""
Angel One SmartAPI Client Wrapper
Uses official SmartApi library for reliable authentication
"""
import logging
import requests
import pyotp
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from SmartApi import SmartConnect
from config import (
    API_KEY, CLIENT_CODE, PASSWORD, TOTP_SECRET,
    INSTRUMENT_URL, MAX_RETRIES, RETRY_DELAY
)

logger = logging.getLogger(__name__)

# Shared client for collector + instrument manager (single session, one TOTP login).
_client_singleton: Optional["AngelOneClient"] = None


def get_client() -> "AngelOneClient":
    """Return a process-wide Angel One client (lazy singleton)."""
    global _client_singleton
    if _client_singleton is None:
        _client_singleton = AngelOneClient()
    return _client_singleton


class AngelOneClient:
    """Wrapper for Angel One SmartAPI using official library"""
    
    def __init__(self):
        self.api_key = API_KEY
        self.client_code = CLIENT_CODE
        self.password = PASSWORD
        self.totp_secret = TOTP_SECRET
        
        self.smart_api = SmartConnect(api_key=self.api_key)
        self.jwt_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.feed_token: Optional[str] = None
        self.token_expiry: Optional[datetime] = None
        self.is_logged_in = False
    
    def _generate_totp(self) -> str:
        """Generate TOTP for login"""
        totp = pyotp.TOTP(self.totp_secret)
        return totp.now()
    
    def login(self) -> bool:
        """Login to Angel One SmartAPI"""
        try:
            totp = self._generate_totp()
            
            data = self.smart_api.generateSession(
                self.client_code,
                self.password,
                totp,
            )

            # generateSession returns getProfile() on success, login JSON on failure.
            # Always read tokens from SmartConnect — that is what optionGreek uses.
            if not data.get("status"):
                logger.error("Login failed: %s", data.get("message"))
                return False

            self.jwt_token = self.smart_api.access_token
            self.refresh_token = self.smart_api.refresh_token
            self.feed_token = self.smart_api.feed_token or self.smart_api.getfeedToken()
            self.token_expiry = datetime.now() + timedelta(hours=8)
            self.is_logged_in = True

            logger.info("Successfully logged in to Angel One SmartAPI")
            return True
                
        except Exception as e:
            logger.error(f"Login error: {str(e)}")
            return False
    
    def refresh_session(self) -> bool:
        """Refresh the JWT token"""
        try:
            if not self.refresh_token:
                logger.warning("No refresh token, attempting full login")
                return self.login()
            
            data = self.smart_api.generateToken(self.refresh_token)

            if data.get("status"):
                self.jwt_token = self.smart_api.access_token
                self.feed_token = self.smart_api.feed_token or self.feed_token
                new_refresh = data.get("data", {}).get("refreshToken")
                if new_refresh:
                    self.refresh_token = new_refresh
                self.token_expiry = datetime.now() + timedelta(hours=8)
                logger.info("Session refreshed successfully")
                return True
            else:
                logger.warning("Token refresh failed, attempting full login")
                return self.login()
                
        except Exception as e:
            logger.error(f"Refresh error: {str(e)}")
            return self.login()
    
    def ensure_authenticated(self) -> bool:
        """Ensure we have a valid session"""
        if not self.is_logged_in:
            return self.login()
        
        if self.token_expiry and datetime.now() >= self.token_expiry:
            logger.info("Token expired, refreshing...")
            return self.refresh_session()
        
        return True
    
    def get_option_greeks(self, underlying: str, expiry_date: str) -> Optional[Dict]:
        """Fetch option Greeks using SmartAPI library"""
        if not self.ensure_authenticated():
            logger.error("Authentication failed")
            return None
        
        for attempt in range(MAX_RETRIES):
            try:
                # Use the SmartAPI optionGreek method
                data = self.smart_api.optionGreek({
                    "name": underlying,
                    "expirydate": expiry_date
                })
                
                if data and (data.get('status') or data.get('data')):
                    logger.debug(f"Fetched Greeks for {underlying} {expiry_date}")
                    return data
                else:
                    error_msg = data.get('message', 'Unknown error') if data else 'No response'
                    logger.warning(f"Greeks API error: {error_msg}")
                    
                    # Check for auth errors
                    if data and data.get('errorcode') in ['AG8001', 'AG8002', 'AB1010']:
                        logger.info("Token issue, refreshing session...")
                        self.refresh_session()
                        continue
                    
                    return data
                    
            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed: {str(e)}")
                if attempt < MAX_RETRIES - 1:
                    import time
                    time.sleep(RETRY_DELAY)
                    self.refresh_session()
        
        return None
    
    def download_instruments(self) -> List[Dict]:
        """Download instrument master file"""
        try:
            logger.info("Downloading instrument master file...")
            response = requests.get(INSTRUMENT_URL, timeout=60)
            response.raise_for_status()
            
            instruments = response.json()
            logger.info(f"Downloaded {len(instruments)} instruments")
            return instruments
            
        except Exception as e:
            logger.error(f"Error downloading instruments: {str(e)}")
            return []
    
    def get_ltp(self, exchange: str, symbol: str, token: str) -> Optional[Dict]:
        """Get last traded price"""
        if not self.ensure_authenticated():
            return None
        
        try:
            data = self.smart_api.ltpData(exchange, symbol, token)
            return data
        except Exception as e:
            logger.error(f"LTP error: {str(e)}")
            return None
    
    def logout(self):
        """Logout from SmartAPI"""
        try:
            if self.is_logged_in:
                self.smart_api.terminateSession(self.client_code)
                self.is_logged_in = False
                logger.info("Logged out successfully")
        except Exception as e:
            logger.error(f"Logout error: {str(e)}")