"""
Configuration file for Angel One SmartAPI Greeks Collector
Update these values with your credentials before running
"""

# Angel One SmartAPI Credentials
API_KEY = "your_api_key_here"
CLIENT_CODE = "your_client_code_here"  # Angel One Client ID
PASSWORD = "your_mpin_here"  # Your MPIN/PIN
TOTP_SECRET = "your_totp_secret_here"  # QR code token for TOTP generation

# Database Configuration
DATABASE_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "greeks_db",
    "user": "postgres",
    "password": "your_db_password_here"
}

# Instrument Master URL
INSTRUMENT_URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"

# Option Greeks API Endpoint
GREEKS_API_URL = "https://apiconnect.angelbroking.com/rest/secure/angelbroking/marketData/v1/optionGreek"

# API Base URL
API_BASE_URL = "https://apiconnect.angelone.in"

# Indices to track for Greeks
INDICES_TO_TRACK = [
    "NIFTY",
    "BANKNIFTY",
    "FINNIFTY",
    "MIDCPNIFTY",
    "SENSEX",
    "BANKEX"
]

# Data collection interval in seconds (60 = 1 minute)
COLLECTION_INTERVAL = 60

# Market hours (IST)
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 15
MARKET_CLOSE_HOUR = 15
MARKET_CLOSE_MINUTE = 30

# Logging configuration
LOG_LEVEL = "INFO"
LOG_FILE = "greeks_collector.log"

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds
