from sqlalchemy import BigInteger, Column, Date, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime

from database import Base
import security


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)

    # SaaS subscription configuration
    plan_tier = Column(String, default="trial")  # trial / pro / expert / guru
    lending_limit = Column(Float, default=250_000.0)
    rebalance_interval = Column(Integer, default=3)  # minutes
    pro_expiry = Column(DateTime, nullable=True)

    # Referrals
    referral_code = Column(String, unique=True, index=True, nullable=True)
    referred_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Lifecycle status – used by the kill switch
    status = Column(String, default="active")  # active / expired

    # Bot process state (updated by API on start/stop and by worker on run/exit)
    bot_status = Column(String, default="stopped")  # stopped | running | starting

    # Relationships
    vault = relationship("APIVault", back_populates="user", uselist=False)
    logs = relationship("PerformanceLog", back_populates="user")
    referrer = relationship("User", remote_side=[id])


class APIVault(Base):
    """
    Stores encrypted Bitfinex API credentials for a single user.
    AES-256 is handled by the security module.
    """

    __tablename__ = "api_vault"

    # One row per user
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)

    encrypted_key = Column(String, nullable=False)
    encrypted_secret = Column(String, nullable=False)

    # Optional extra key used by the engine (e.g., Gemini/Gemini AI key)
    encrypted_gemini_key = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=True)
    last_tested_at = Column(DateTime, nullable=True)
    last_test_balance = Column(Float, nullable=True)

    user = relationship("User", back_populates="vault")

    def get_keys(self) -> dict:
        """
        Decrypts the stored keys for the worker using the security module.
        """
        return {
            "bfx_key": security.decrypt_key(self.encrypted_key),
            "bfx_secret": security.decrypt_key(self.encrypted_secret),
            "gemini_key": security.decrypt_key(self.encrypted_gemini_key)
            if self.encrypted_gemini_key
            else "",
        }


class TrialHistory(Base):
    """
    Tracks every Bitfinex master account that has ever used the free trial.
    """

    __tablename__ = "trial_history"

    hashed_bitfinex_id = Column(String, primary_key=True, index=True)


class PerformanceLog(Base):
    """
    Periodic performance snapshots for a user.
    """

    __tablename__ = "performance_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

    # WAROC-style metric (e.g., APR or PnL proxy)
    waroc = Column(Float)

    # Total asset value across funding wallets
    total_assets = Column(Float)

    user = relationship("User", back_populates="logs")


class UserProfitSnapshot(Base):
    """
    Last computed Gross Profit / Net Earnings from lending trade history (since registration).
    Updated when /stats/{user_id}/lending is computed; used for token balance without extra API.
    last_trade_mts: max MTS_CREATE we have synced; next refresh only fetches trades after this (incremental).
    """

    __tablename__ = "user_profit_snapshot"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    gross_profit_usd = Column(Float, default=0.0)
    net_profit_usd = Column(Float, default=0.0)
    bitfinex_fee_usd = Column(Float, default=0.0)
    last_trade_mts = Column(BigInteger, nullable=True)  # incremental: only fetch trades after this
    total_trades_count = Column(Integer, nullable=True)  # cumulative count of trades synced (for display)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # Daily gross for token deduction (set at 09:40 UTC; read at 10:15 UTC)
    daily_gross_profit_usd = Column(Float, default=0.0)  # gross profit for that UTC day
    last_daily_cumulative_gross = Column(Float, nullable=True)  # cumulative gross at last daily snapshot
    last_daily_snapshot_date = Column(Date, nullable=True)  # UTC date of that snapshot


class UserTokenBalance(Base):
    """
    Token credit balance (Cursor-style). 0.1 USD gross profit = 1 token used.
    Initial credit: 100 (free), 1500 (Pro), 9000 (AI Ultra), 40000 (Whales).
    purchased_tokens: extra tokens from custom USD purchase (1 USD = 100 tokens).
    """

    __tablename__ = "user_token_balance"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    tokens_remaining = Column(Float, default=0.0)
    last_gross_usd_used = Column(Float, default=0.0)  # gross_profit_usd at last token calc
    purchased_tokens = Column(Float, default=0.0)  # tokens bought via Add tokens (1 USD = 100)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)