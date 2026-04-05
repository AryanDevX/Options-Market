"""
Angel One SmartAPI Client Wrapper
Handles authentication, session management, and API calls
"""

import json
import time
import logging
import requests
import pyotp
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from config import (
    API_KEY, CLIENT_CODE, PASSWORD, TOTP_SECRET,
    API_BASE_URL, GREEKS_API_URL, INSTRUMENT_URL,
    MAX_RETRIES, RETRY_DELAY
)

logger = logging.getLogger(__name__)


class AngelOneClient:
    """Wrapper for Angel One SmartAPI"""
    
    def __init__(self):
        self.api_key = API_KEY
        self.client_code = CLIENT_CODE
        self.password = PASSWORD
        self.totp_secret = TOTP_SECRET
        
        self.jwt_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.feed_token: Optional[str] = None
        self.token_expiry: Optional[datetime] = None
        
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'X-UserType': 'USER',
            'X-SourceID': 'WEB',
            'X-ClientLocalIP': '127.0.0.1',
            'X-ClientPublicIP': '127.0.0.1',
            'X-MACAddress': '00:00:00:00:00:00',
            'X-PrivateKey': self.api_key
        })
    
    def _generate_totp(self) -> str:
        """Generate TOTP for login"""
        totp = pyotp.TOTP(self.totp_secret)
        return totp.now()
    
    def login(self) -> bool:
        """
        Login to Angel One SmartAPI
        Returns True on success, False on failure
        """
        try:
            totp = self._generate_totp()
            
            login_url = f"{API_BASE_URL}/rest/auth/angelbroking/user/v1/loginByPassword"
            
            payload = {
                "clientcode": self.client_code,
                "password": self.password,
                "totp": totp
            }
            
            response = self.session.post(login_url, json=payload)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('status'):
                self.jwt_token = data['data']['jwtToken']
                self.refresh_token = data['data']['refreshToken']
                self.feed_token = data['data'].get('feedToken')
                self.token_expiry = datetime.now() + timedelta(hours=8)
                
                # Update session headers with auth token
                self.session.headers.update({
                    'Authorization': f'Bearer {self.jwt_token}'
                })
                
                logger.info("Successfully logged in to Angel One SmartAPI")
                return True
            else:
                logger.error(f"Login failed: {data.get('message')}")
                return False
                
        except Exception as e:
            logger.error(f"Login error: {str(e)}")
            return False
    
    def refresh_session(self) -> bool:
        """Refresh the JWT token using refresh token"""
        try:
            if not self.refresh_token:
                return self.login()
            
            refresh_url = f"{API_BASE_URL}/rest/auth/angelbroking/jwt/v1/generateTokens"
            
            payload = {
                "refreshToken": self.refresh_token
            }
            
            response = self.session.post(refresh_url, json=payload)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('status'):
                self.jwt_token = data['data']['jwtToken']
                self.refresh_token = data['data']['refreshToken']
                self.token_expiry = datetime.now() + timedelta(hours=8)
                
                self.session.headers.update({
                    'Authorization': f'Bearer {self.jwt_token}'
                })
                
                logger.info("Session refreshed successfully")
                return True
            else:
                logger.warning("Token refresh failed, attempting full login")
                return self.login()
                
        except Exception as e:
            logger.error(f"Session refresh error: {str(e)}")
            return self.login()
    
    def ensure_authenticated(self) -> bool:
        """Ensure we have a valid session"""
        if not self.jwt_token:
            return self.login()
        
        if self.token_expiry and datetime.now() > self.token_expiry - timedelta(minutes=30):
            return self.refresh_session()
        
        return True
    
    def download_instruments(self) -> List[Dict]:
        """
        Download complete instrument master file
        Returns list of all instruments (stocks, indices, options, futures)
        """
        logger.info("Downloading instrument master file...")
        
        for attempt in range(MAX_RETRIES):
            try:
                response = requests.get(INSTRUMENT_URL, timeout=60)
                response.raise_for_status()
                
                instruments = response.json()
                logger.info(f"Downloaded {len(instruments)} instruments")
                return instruments
                
            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed: {str(e)}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
        
        return []
    
    def get_option_greeks(self, underlying: str, expiry_date: str) -> Optional[Dict]:
        """
        Fetch option Greeks for an underlying and expiry
        
        Args:
            underlying: Index/Stock name (e.g., "NIFTY", "BANKNIFTY")
            expiry_date: Expiry date in format "25JAN2024"
        
        Returns:
            Dict with Greeks data or None on failure
        """
        if not self.ensure_authenticated():
            logger.error("Authentication failed")
            return None
        
        for attempt in range(MAX_RETRIES):
            try:
                payload = {
                    "name": underlying,
                    "expirydate": expiry_date
                }
                
                response = self.session.post(GREEKS_API_URL, json=payload)
                response.raise_for_status()
                
                data = response.json()
                
                if data.get('status') or data.get('success'):
                    logger.debug(f"Fetched Greeks for {underlying} {expiry_date}")
                    return data
                else:
                    logger.warning(f"Greeks API returned error: {data.get('message')}")
                    
                    # Check for auth errors
                    if data.get('errorCode') in ['AG8001', 'AG8002']:
                        logger.info("Token expired, refreshing session...")
                        self.refresh_session()
                        continue
                    
                    return data
                    
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 401:
                    logger.info("Unauthorized, refreshing session...")
                    self.refresh_session()
                    continue
                logger.error(f"HTTP error: {str(e)}")
                
            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed: {str(e)}")
            
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
        
        return None
    
    def get_ltp(self, exchange: str, symbol: str, token: str) -> Optional[Dict]:
        """Get Last Traded Price for a symbol"""
        if not self.ensure_authenticated():
            return None
        
        try:
            url = f"{API_BASE_URL}/rest/secure/angelbroking/order/v1/getLtpData"
            
            payload = {
                "exchange": exchange,
                "tradingsymbol": symbol,
                "symboltoken": token
            }
            
            response = self.session.post(url, json=payload)
            response.raise_for_status()
            
            return response.json()
            
        except Exception as e:
            logger.error(f"LTP fetch error: {str(e)}")
            return None
    
    def get_market_data(self, exchange: str, tokens: List[str], mode: str = "FULL") -> Optional[Dict]:
        """
        Get market data for multiple tokens
        
        Args:
            exchange: Exchange segment (NSE, NFO, etc.)
            tokens: List of symbol tokens
            mode: LTP, OHLC, or FULL
        """
        if not self.ensure_authenticated():
            return None
        
        try:
            url = f"{API_BASE_URL}/rest/secure/angelbroking/market/v1/quote"
            
            payload = {
                "mode": mode,
                "exchangeTokens": {
                    exchange: tokens
                }
            }
            
            response = self.session.post(url, json=payload)
            response.raise_for_status()
            
            return response.json()
            
        except Exception as e:
            logger.error(f"Market data fetch error: {str(e)}")
            return None
    
    def logout(self) -> bool:
        """Logout from Angel One SmartAPI"""
        try:
            if not self.jwt_token:
                return True
            
            url = f"{API_BASE_URL}/rest/secure/angelbroking/user/v1/logout"
            
            payload = {
                "clientcode": self.client_code
            }
            
            response = self.session.post(url, json=payload)
            
            self.jwt_token = None
            self.refresh_token = None
            self.feed_token = None
            self.token_expiry = None
            
            logger.info("Logged out successfully")
            return True
            
        except Exception as e:
            logger.error(f"Logout error: {str(e)}")
            return False


# Singleton instance
_client: Optional[AngelOneClient] = None


def get_client() -> AngelOneClient:
    """Get or create the Angel One client instance"""
    global _client
    if _client is None:
        _client = AngelOneClient()
    return _client
