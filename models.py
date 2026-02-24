from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base
import security  # Crucial: This allows the model to decrypt keys on the fly

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    
    vault = relationship("APIKeyVault", back_populates="owner", uselist=False)
    logs = relationship("PerformanceLog", back_populates="owner")

class APIKeyVault(Base):
    __tablename__ = "api_key_vaults"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    
    # Encrypted strings
    encrypted_bfx_key = Column(String)
    encrypted_bfx_secret = Column(String)
    encrypted_gemini_key = Column(String)

    owner = relationship("User", back_populates="vault")

    def get_keys(self) -> dict:
        """
        Decrypts the stored keys for the worker using the security module.
        """
        return {
            "bfx_key": security.decrypt_key(self.encrypted_bfx_key),
            "bfx_secret": security.decrypt_key(self.encrypted_bfx_secret),
            "gemini_key": security.decrypt_key(self.encrypted_gemini_key)
        }

class PerformanceLog(Base):
    __tablename__ = "performance_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    currency = Column(String)
    waroc_apr = Column(Float)
    total_loaned = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="logs")