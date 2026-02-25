from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
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