# Angel One SmartAPI Greeks Collector

A production-ready system to collect option Greeks data from Angel One SmartAPI every minute and store it in PostgreSQL. Designed for deployment on AWS with cost optimization.

## 📋 Features

- **Download complete instrument master** (stocks, indices, options, futures)
- **Automatic nearest expiry detection** for major indices (NIFTY, BANKNIFTY, FINNIFTY, etc.)
- **Greeks collection every minute** during market hours
- **PostgreSQL storage** with optimized indexes
- **Systemd service** for daemon mode
- **Web dashboard** for monitoring
- **AWS Terraform** infrastructure as code
- **CloudWatch integration** for logging

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         AWS Cloud                                 │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                    EC2 (t3.small)                          │  │
│  │  ┌──────────────────────────────────────────────────────┐  │  │
│  │  │              Greeks Collector Service                 │  │  │
│  │  │  ┌────────────┐  ┌────────────┐  ┌────────────────┐  │  │  │
│  │  │  │ Instrument │  │   Greeks   │  │   Dashboard    │  │  │  │
│  │  │  │  Manager   │──│ Collector  │──│   (Flask)      │  │  │  │
│  │  │  └────────────┘  └────────────┘  └────────────────┘  │  │  │
│  │  └──────────────────────────────────────────────────────┘  │  │
│  └────────────────────────────────────────────────────────────┘  │
│                              │                                    │
│                              ▼                                    │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │        PostgreSQL (local or RDS db.t3.micro)               │  │
│  │  ┌─────────────┐ ┌─────────────┐ ┌───────────────────────┐ │  │
│  │  │ instruments │ │index_expiry │ │    option_greeks      │ │  │
│  │  └─────────────┘ └─────────────┘ └───────────────────────┘ │  │
│  └────────────────────────────────────────────────────────────┘  │
│                              │                                    │
│                              ▼                                    │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                CloudWatch Logs & Alarms                    │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                    Angel One SmartAPI                             │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────────┐  │
│  │ Instruments    │  │ Option Greeks  │  │ Market Data        │  │
│  │ Master JSON    │  │ API            │  │ API                │  │
│  └────────────────┘  └────────────────┘  └────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

## 💰 AWS Cost Estimation

With your $100 credit over 184 days (~6 months):

### Option 1: EC2 + Local PostgreSQL (Recommended) - ~$18/month
| Resource | Monthly Cost |
|----------|-------------|
| EC2 t3.small | $15.18 |
| EBS 30GB gp3 | $2.40 |
| Data Transfer | ~$1 |
| **Total** | **~$18.50** |

**Total for 184 days: ~$113** (slightly over, reduce to t3.micro to fit)

### Option 2: EC2 + RDS - ~$32/month
| Resource | Monthly Cost |
|----------|-------------|
| EC2 t3.small | $15.18 |
| RDS db.t3.micro | $12.41 |
| EBS 30GB gp3 | $2.40 |
| Data Transfer | ~$1 |
| **Total** | **~$31** |

**Total for 184 days: ~$190** (over budget)

### Recommendation
Use **EC2 t3.micro ($7.50/month) + Local PostgreSQL** to stay within budget.

## 🚀 Quick Start

### Prerequisites

1. **Angel One Trading Account** with SmartAPI enabled
2. **SmartAPI Credentials:**
   - API Key (from SmartAPI Developer Portal)
   - Client Code (your Angel One client ID)
   - MPIN/Password
   - TOTP Secret (QR code token)

### Local Setup

```bash
# Clone or download the files
cd angelone_greeks_collector

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Setup PostgreSQL (Ubuntu/Debian)
sudo apt install postgresql postgresql-contrib
sudo -u postgres createuser -P greeks_user  # Set password
sudo -u postgres createdb -O greeks_user greeks_db

# Edit configuration
cp config.py config_local.py
nano config.py  # Add your credentials

# Initialize database
python -c "from models import init_database; init_database()"

# Run the collector
python greeks_collector.py
```

### AWS Deployment

```bash
# Option 1: Using deployment script
chmod +x deploy_aws.sh
./deploy_aws.sh

# Option 2: Using Terraform
cd infrastructure
terraform init
terraform plan
terraform apply
```

## 📁 Project Structure

```
angelone_greeks_collector/
├── config.py              # Configuration and credentials
├── models.py              # SQLAlchemy database models
├── api_client.py          # Angel One API wrapper
├── instrument_manager.py  # Instrument download and expiry detection
├── greeks_collector.py    # Main collector service
├── dashboard.py           # Flask monitoring dashboard
├── requirements.txt       # Python dependencies
├── greeks-collector.service  # Systemd service file
├── deploy_aws.sh          # AWS deployment script
└── infrastructure/
    └── main.tf            # Terraform configuration
```

## 🔧 Configuration

Edit `config.py` with your credentials:

```python
# Angel One SmartAPI Credentials
API_KEY = "your_api_key_here"
CLIENT_CODE = "your_client_code"  # Angel One Client ID
PASSWORD = "your_mpin"
TOTP_SECRET = "your_totp_secret"  # From QR code

# Database
DATABASE_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "greeks_db",
    "user": "greeks_user",
    "password": "your_db_password"
}

# Indices to track
INDICES_TO_TRACK = [
    "NIFTY",
    "BANKNIFTY",
    "FINNIFTY",
    "MIDCPNIFTY"
]
```

## 📊 Database Schema

### `instruments` table
Stores all instruments from the master file:
- token, symbol, name
- expiry, strike, lotsize
- instrumenttype, exch_seg

### `index_expiries` table
Tracks nearest expiry for each index:
- index_name, nearest_expiry
- expiry_type (weekly/monthly)

### `option_greeks` table
Stores Greeks data collected every minute:
- timestamp, underlying, expiry_date
- strike_price, option_type
- delta, gamma, theta, vega, implied_volatility
- ltp, open_interest, volume

### `collection_logs` table
Logs each collection run:
- timestamp, status, records_collected
- error_message, duration_ms

## 🖥️ Monitoring Dashboard

Start the dashboard:
```bash
python dashboard.py
```

Access at: `http://localhost:5000`

Features:
- Collection statistics (24h)
- Tracked expiries and days to expiry
- Recent collection logs
- Sample Greeks data
- Health check API: `/api/health`

## 🛠️ Service Management

```bash
# Start service
sudo systemctl start greeks-collector

# Stop service
sudo systemctl stop greeks-collector

# Check status
sudo systemctl status greeks-collector

# View logs
journalctl -u greeks-collector -f

# Restart on config changes
sudo systemctl restart greeks-collector
```

## 📈 Data Analysis Queries

```sql
-- Get latest Greeks for NIFTY ATM options
SELECT * FROM option_greeks 
WHERE underlying = 'NIFTY' 
  AND timestamp = (SELECT MAX(timestamp) FROM option_greeks WHERE underlying = 'NIFTY')
ORDER BY ABS(strike_price - 24000)  -- Replace 24000 with current NIFTY level
LIMIT 20;

-- IV history for a specific strike
SELECT timestamp, implied_volatility, ltp
FROM option_greeks
WHERE underlying = 'BANKNIFTY'
  AND strike_price = 51000
  AND option_type = 'CE'
ORDER BY timestamp;

-- Collection success rate
SELECT 
  DATE(timestamp) as date,
  COUNT(*) FILTER (WHERE status = 'success') as successful,
  COUNT(*) FILTER (WHERE status = 'failed') as failed,
  ROUND(AVG(records_collected)) as avg_records
FROM collection_logs
GROUP BY DATE(timestamp)
ORDER BY date DESC;
```

## ⚠️ Rate Limits

Angel One SmartAPI has rate limits:
- Orders: 10 requests/second
- Market Data: Varies by endpoint
- Greeks API: Typically 1-2 requests/second

The collector includes delays between API calls to respect limits.

## 🔒 Security Notes

1. **Never commit credentials** to version control
2. Use **environment variables** or AWS Secrets Manager in production
3. Restrict **security group** access to your IP only
4. Enable **RDS encryption** if using managed database
5. Use **IAM roles** instead of access keys on EC2

## 🐛 Troubleshooting

### Login Failed
- Check API Key and Client Code
- Verify TOTP secret is correct
- Ensure MPIN/Password is correct

### No Greeks Data
- Verify market is open (9:15 AM - 3:30 PM IST)
- Check if expiry date format is correct
- Look for API error messages in logs

### Database Connection Failed
- Verify PostgreSQL is running
- Check database credentials
- Ensure database exists

### Token Expired
- The collector auto-refreshes tokens
- Check logs for authentication errors
- Verify your account is active

## 📝 License

MIT License - Free for personal and commercial use.

## 🙏 Acknowledgments

- [Angel One SmartAPI](https://smartapi.angelbroking.com/)
- [SQLAlchemy](https://www.sqlalchemy.org/)
- [Flask](https://flask.palletsprojects.com/)
