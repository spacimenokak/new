from sqlalchemy import Column, BigInteger, String, Boolean, DateTime
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String, nullable=True)
    name = Column(String, nullable=True)
    age = Column(BigInteger, nullable=True)
    city = Column(String, nullable=True)
    is_registered = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)