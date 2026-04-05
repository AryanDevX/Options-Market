"""
Database models and setup for Greeks data storage
Uses PostgreSQL with SQLAlchemy ORM
"""

import os
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, DateTime, 
    Date, BigInteger, Index, Text, Boolean
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from config import DATABASE_CONFIG

Base = declarative_base()


class Instrument(Base):
    """Store all instruments from Angel One master file"""
    __tablename__ = 'instruments'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    token = Column(String(20), index=True)
    symbol = Column(String(100), index=True)
    name = Column(String(100), index=True)
    expiry = Column(Date, nullable=True, index=True)
    strike = Column(Float, nullable=True)
    lotsize = Column(Integer, nullable=True)
    instrumenttype = Column(String(20), index=True)
    exch_seg = Column(String(10), index=True)
    tick_size = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_instrument_lookup', 'symbol', 'exch_seg'),
        Index('idx_instrument_expiry', 'name', 'expiry', 'instrumenttype'),
    )


class IndexExpiry(Base):
    """Store nearest expiry information for each index"""
    __tablename__ = 'index_expiries'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    index_name = Column(String(50), index=True)
    nearest_expiry = Column(Date, index=True)
    expiry_type = Column(String(20))  # weekly, monthly
    updated_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_index_expiry', 'index_name', 'nearest_expiry'),
    )


class OptionGreeks(Base):
    """Store option greeks data collected every minute"""
    __tablename__ = 'option_greeks'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, index=True, default=datetime.utcnow)
    underlying = Column(String(50), index=True)
    expiry_date = Column(Date, index=True)
    strike_price = Column(Float, index=True)
    option_type = Column(String(2))  # CE or PE
    token = Column(String(20))
    symbol = Column(String(100))
    
    # Greeks
    delta = Column(Float, nullable=True)
    gamma = Column(Float, nullable=True)
    theta = Column(Float, nullable=True)
    vega = Column(Float, nullable=True)
    implied_volatility = Column(Float, nullable=True)
    
    # Price data
    ltp = Column(Float, nullable=True)
    open_interest = Column(BigInteger, nullable=True)
    volume = Column(BigInteger, nullable=True)
    bid_price = Column(Float, nullable=True)
    ask_price = Column(Float, nullable=True)
    
    # Metadata
    raw_response = Column(Text, nullable=True)  # Store raw JSON for debugging
    
    __table_args__ = (
        Index('idx_greeks_lookup', 'underlying', 'expiry_date', 'timestamp'),
        Index('idx_greeks_strike', 'underlying', 'strike_price', 'option_type'),
        Index('idx_greeks_time', 'timestamp', 'underlying'),
    )


class CollectionLog(Base):
    """Log each data collection run"""
    __tablename__ = 'collection_logs'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    index_name = Column(String(50))
    expiry_date = Column(Date)
    status = Column(String(20))  # success, failed, partial
    records_collected = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=True)


class SessionToken(Base):
    """Store API session tokens"""
    __tablename__ = 'session_tokens'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    jwt_token = Column(Text)
    refresh_token = Column(Text)
    feed_token = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)


def get_database_url():
    """Build PostgreSQL connection URL"""
    return (
        f"postgresql://{DATABASE_CONFIG['user']}:{DATABASE_CONFIG['password']}"
        f"@{DATABASE_CONFIG['host']}:{DATABASE_CONFIG['port']}/{DATABASE_CONFIG['database']}"
    )


def create_db_engine():
    """Create SQLAlchemy engine with connection pooling"""
    return create_engine(
        get_database_url(),
        poolclass=QueuePool,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        echo=False
    )


def init_database():
    """Initialize database tables"""
    engine = create_db_engine()
    Base.metadata.create_all(engine)
    print("Database tables created successfully!")
    return engine


def get_session():
    """Get a new database session"""
    engine = create_db_engine()
    Session = sessionmaker(bind=engine)
    return Session()


if __name__ == "__main__":
    # Create tables when run directly
    init_database()
