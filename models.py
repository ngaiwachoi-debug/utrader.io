from sqlalchemy import BigInteger, Boolean, Column, Date, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from datetime import datetime

from database import Base
import security


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=True)

    # SaaS subscription configuration
    plan_tier = Column(String, default="trial")  # trial / pro / expert / guru
    lending_limit = Column(Float, default=250_000.0)
    rebalance_interval = Column(Integer, default=3)  # minutes
    pro_expiry = Column(DateTime, nullable=True)

    # Referrals
    referral_code = Column(String, unique=True, index=True, nullable=True)
    referred_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    usdt_withdraw_address = Column(String(255), nullable=True)

    # Lifecycle status – used by the kill switch
    status = Column(String, default="active")  # active / expired

    # Bot process state (updated by API on start/stop and by worker on run/exit)
    bot_status = Column(String, default="stopped")  # stopped | running | starting
    # Desired state (Plan C): running | stopped; worker reconciles to this
    bot_desired_state = Column(String(20), default="stopped")  # running | stopped

    # Monthly API key deletion count for abuse detection (persisted; {"YYYY-MM": count})
    key_deletions = Column(Text, default="{}", nullable=True)  # JSON: {"2026-02": 2}

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
    keys_updated_at = Column(DateTime, nullable=True)  # set when API keys are saved; used to detect Bitfinex account change

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
    last_vault_updated_at = Column(DateTime, nullable=True)  # vault.keys_updated_at at last 09:40 run; detect account switch
    account_switch_note = Column(Text, nullable=True)  # set at 09:40 when Bitfinex account changed; read at 10:15 for DeductionLog then cleared
    # Prevent double-charge: set True after 10:30/11:15 deduction for date_utc
    deduction_processed = Column(Boolean, default=False, nullable=True)
    last_deduction_processed_date = Column(Date, nullable=True)  # UTC date for which deduction was run
    invalid_key_days = Column(Integer, default=0, nullable=True)  # consecutive days API key invalid; reset only on key restore
    last_cached_daily_gross_usd = Column(Float, nullable=True)  # set when 10:30 used cache; for reconciliation at 11:15
    reconciliation_completed = Column(Boolean, default=True, nullable=True)  # False when key restored post-11:15; 23:00 sweep sets True


class UserTokenBalance(Base):
    """
    Token balance (legacy schema). Single source of truth: tokens_remaining.
    purchased_tokens = amount from deposit/subscription/admin (for referral burn logic).
    """

    __tablename__ = "user_token_balance"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    tokens_remaining = Column(Float, default=0.0, nullable=False)
    last_gross_usd_used = Column(Float, default=0.0)  # gross_profit_usd at last deduction
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    purchased_tokens = Column(Float, default=0.0, nullable=False)  # for referral: deposit/subscription/admin


class UserUsdtCredit(Base):
    """Withdrawable USDT balance per user (Token2)."""
    __tablename__ = "user_usdt_credit"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    usdt_credit = Column(Float, default=0.0)  # current withdrawable balance
    total_earned = Column(Float, default=0.0)
    total_withdrawn = Column(Float, default=0.0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UsdtHistory(Base):
    """History of USDT credit changes (admin adjust, withdrawal, referral earnings, etc.)."""
    __tablename__ = "usdt_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    amount = Column(Float, nullable=False)  # positive = credit, negative = debit
    reason = Column(String(64), nullable=True)  # admin_adjust, withdrawal, referral_earnings, etc.
    created_at = Column(DateTime, default=datetime.utcnow)
    admin_email = Column(String(255), nullable=True)


class WithdrawalRequest(Base):
    """User withdrawal request; admin approve/reject."""
    __tablename__ = "withdrawal_requests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    amount = Column(Float, nullable=False)
    address = Column(String(255), nullable=False)
    status = Column(String(32), default="pending")  # pending | approved | rejected
    created_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)
    processed_by = Column(String(255), nullable=True)
    rejection_note = Column(String(500), nullable=True)


class ReferralReward(Base):
    """Immutable log of referral rewards (L1/L2/L3 USDT Credit per purchased token burn)."""
    __tablename__ = "referral_rewards"

    id = Column(Integer, primary_key=True, index=True)
    burning_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    level_1_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    level_2_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    level_3_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    reward_l1 = Column(Float, default=0.0)
    reward_l2 = Column(Float, default=0.0)
    reward_l3 = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)


class DeductionLog(Base):
    """Persisted token deduction log (10:15 UTC). used_tokens = gross_profit_usd × TOKENS_PER_USDT_GROSS (10)."""
    __tablename__ = "deduction_log"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    email = Column(String(255), nullable=True)
    timestamp_utc = Column(DateTime, nullable=False)
    daily_gross_profit_usd = Column(Float, default=0.0)
    tokens_deducted = Column(Float, default=0.0)  # 1:1 USD for that day
    total_used_tokens = Column(Float, nullable=True)  # int(gross_profit_usd * 10) at snapshot time
    tokens_remaining_after = Column(Float, nullable=True)
    account_switch_note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class AdminNotification(Base):
    """Global or per-user announcement."""
    __tablename__ = "admin_notifications"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=True)
    type = Column(String(32), default="info")  # info | warning | announcement
    target_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # null = all users
    created_at = Column(DateTime, default=datetime.utcnow)


class AdminSetting(Base):
    """Key-value platform config (registration bonus, min withdrawal, etc.)."""
    __tablename__ = "admin_settings"

    key = Column(String(128), primary_key=True)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AdminAuditLog(Base):
    """Persistent audit log (no delete)."""
    __tablename__ = "admin_audit_log"

    id = Column(Integer, primary_key=True, index=True)
    ts = Column(DateTime, default=datetime.utcnow, nullable=False)
    email = Column(String(255), nullable=False)
    action = Column(String(64), nullable=False)
    detail = Column(Text, nullable=True)  # JSON string