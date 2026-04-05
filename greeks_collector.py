import time
import sqlite3
import os
import pandas as pd
import pyotp
import logging
from datetime import datetime
from SmartApi import SmartConnect

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# ─── CONFIG ───────────────────────────────────────────
API_KEY    = os.environ['API_KEY']
USERNAME   = os.environ['USERNAME']
PWD        = os.environ['PASSWORD']
TOKEN      = os.environ['TOTP_SECRET']
SYMBOL     = 'NIFTY'
EXPIRY     = '07APR2026'
INTERVAL   = 60  # seconds
DB_FILE    = 'greeks.db'
# ──────────────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS greeks (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp     TEXT,
            name          TEXT,
            expiry        TEXT,
            strike_price  REAL,
            option_type   TEXT,
            delta         REAL,
            gamma         REAL,
            theta         REAL,
            vega          REAL,
            iv            REAL,
            trade_volume  REAL
        )
    ''')
    conn.commit()
    conn.close()
    logger.info("Database initialized")

def login():
    smartApi = SmartConnect(API_KEY)
    totp = pyotp.TOTP(TOKEN).now()
    data = smartApi.generateSession(USERNAME, PWD, totp)
    if data['status']:
        logger.info("Login successful")
        return smartApi
    else:
        raise Exception(f"Login failed: {data['message']}")

def is_market_open():
    now = datetime.now()
    # Skip weekends
    if now.weekday() >= 5:
        return False
    # Market hours: 9:15 AM to 3:30 PM IST
    start = now.replace(hour=9, minute=15, second=0)
    end   = now.replace(hour=15, minute=30, second=0)
    return start <= now <= end

def fetch_and_store(smartApi):
    try:
        params = {"name": SYMBOL, "expirydate": EXPIRY}
        response = smartApi.optionGreek(params)

        if not response['status']:
            logger.warning(f"API error: {response['message']}")
            return

        df = pd.DataFrame(response['data'])
        df['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        df['name']      = SYMBOL
        df['expiry']    = EXPIRY

        # Save to DB
        conn = sqlite3.connect(DB_FILE)
        df.rename(columns={
            'strikePrice':   'strike_price',
            'optionType':    'option_type',
            'impliedVolatility': 'iv',
            'tradeVolume':   'trade_volume'
        }, inplace=True)

        df[['timestamp','name','expiry','strike_price','option_type',
            'delta','gamma','theta','vega','iv','trade_volume']].to_sql(
            'greeks', conn, if_exists='append', index=False
        )
        conn.close()
        logger.info(f"Saved {len(df)} rows at {df['timestamp'].iloc[0]}")

    except Exception as e:
        logger.error(f"Error: {e}")

def main():
    init_db()
    smartApi = login()

    logger.info("Waiting for market hours...")
    while True:
        if is_market_open():
            fetch_and_store(smartApi)
            time.sleep(INTERVAL)
        else:
            now = datetime.now()
            # Re-login fresh each morning
            if now.hour == 9 and now.minute == 14:
                smartApi = login()
            logger.info(f"Market closed. Sleeping... [{now.strftime('%H:%M')}]")
            time.sleep(30)

if __name__ == "__main__":
    main()