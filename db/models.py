from sqlalchemy import Column, BigInteger, String, Boolean, DateTime, Integer, Float, ForeignKey, CheckConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String, nullable=True)
    name = Column(String, nullable=True)
    age = Column(Integer, nullable=True)
    city = Column(String, nullable=True)
    is_registered = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Profile(Base):
    __tablename__ = "profiles"
    
    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), unique=True)
    name = Column(String(255))
    age = Column(Integer)
    city = Column(String(255))
    bio = Column(String(1000), nullable=True)
    gender = Column(String(20))
    preferred_gender = Column(String(20))
    preferred_age_from = Column(Integer, default=18)
    preferred_age_to = Column(Integer, default=100)
    photo_urls = Column(String, nullable=True)
    is_filled = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Rating(Base):
    __tablename__ = "ratings"
    
    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), unique=True)
    primary_score = Column(Float, default=0.0)
    behavioral_score = Column(Float, default=0.0)
    combined_score = Column(Float, default=0.0)
    total_likes = Column(Integer, default=0)
    total_skips = Column(Integer, default=0)
    total_matches = Column(Integer, default=0)


class Interaction(Base):
    __tablename__ = "interactions"
    
    id = Column(BigInteger, primary_key=True)
    actor_id = Column(BigInteger, ForeignKey("users.telegram_id"))
    target_id = Column(BigInteger, ForeignKey("users.telegram_id"))
    type = Column(String(10))
    created_at = Column(DateTime, default=datetime.utcnow)


class Match(Base):
    __tablename__ = "matches"
    
    id = Column(BigInteger, primary_key=True)
    user1_id = Column(BigInteger, ForeignKey("users.telegram_id"))
    user2_id = Column(BigInteger, ForeignKey("users.telegram_id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String(20), default="active")