#!/bin/bash

#############################################
# AWS EC2 Deployment Script for Greeks Collector
# Recommended: t3.small or t3.medium instance
# OS: Ubuntu 22.04 LTS
#############################################

set -e

echo "=========================================="
echo "Angel One Greeks Collector - AWS Setup"
echo "=========================================="

# Update system
echo "Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install Python and PostgreSQL
echo "Installing Python 3.11 and PostgreSQL..."
sudo apt install -y python3.11 python3.11-venv python3-pip postgresql postgresql-contrib

# Install build dependencies
sudo apt install -y build-essential libpq-dev

# Start PostgreSQL
echo "Starting PostgreSQL..."
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Create database and user
echo "Setting up PostgreSQL database..."
sudo -u postgres psql <<EOF
CREATE USER greeks_user WITH PASSWORD 'your_secure_password_here';
CREATE DATABASE greeks_db OWNER greeks_user;
GRANT ALL PRIVILEGES ON DATABASE greeks_db TO greeks_user;
\c greeks_db
GRANT ALL ON SCHEMA public TO greeks_user;
EOF

echo "Database 'greeks_db' created with user 'greeks_user'"

# Create application directory
APP_DIR="/home/ubuntu/angelone_greeks_collector"
echo "Creating application directory at $APP_DIR..."
mkdir -p $APP_DIR
cd $APP_DIR

# Copy application files (assuming they're in current directory)
# In production, you would clone from git or copy from S3
echo "Copy your application files to $APP_DIR"

# Create virtual environment
echo "Creating Python virtual environment..."
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Initialize database tables
echo "Initializing database tables..."
python -c "from models import init_database; init_database()"

# Setup systemd service
echo "Setting up systemd service..."
sudo cp greeks-collector.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable greeks-collector

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "Next Steps:"
echo "1. Edit config.py with your Angel One API credentials:"
echo "   nano $APP_DIR/config.py"
echo ""
echo "2. Update database password in config.py to match above"
echo ""
echo "3. Start the service:"
echo "   sudo systemctl start greeks-collector"
echo ""
echo "4. Check status:"
echo "   sudo systemctl status greeks-collector"
echo ""
echo "5. View logs:"
echo "   journalctl -u greeks-collector -f"
echo ""
echo "=========================================="

# Optional: Setup CloudWatch Logs
read -p "Would you like to setup CloudWatch Logs? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Installing CloudWatch Agent..."
    wget https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb
    sudo dpkg -i amazon-cloudwatch-agent.deb
    
    # Create CloudWatch config
    cat > /tmp/cloudwatch-config.json <<CWEOF
{
    "logs": {
        "logs_collected": {
            "files": {
                "collect_list": [
                    {
                        "file_path": "$APP_DIR/greeks_collector.log",
                        "log_group_name": "greeks-collector",
                        "log_stream_name": "{instance_id}",
                        "timestamp_format": "%Y-%m-%d %H:%M:%S"
                    }
                ]
            }
        }
    }
}
CWEOF

    sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
        -a fetch-config \
        -m ec2 \
        -c file:/tmp/cloudwatch-config.json \
        -s
    
    echo "CloudWatch Logs configured!"
fi

echo ""
echo "AWS Deployment Complete!"
