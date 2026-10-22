import datetime
import os
from dotenv import load_dotenv
from sqlalchemy import Column, DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    # Graceful local fallback if DATABASE_URL is not set
    DATABASE_URL = "sqlite:///./app_local.db"
else:
    # Standardize Postgres URI prefix for SQLAlchemy
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Neon / PostgreSQL connection pool tuning with pool_pre_ping to survive idle timeouts
connect_args = {}
if "sqlite" in DATABASE_URL:
    connect_args = {"check_same_thread": False}
    engine = create_engine(DATABASE_URL, connect_args=connect_args)
else:
    engine = create_engine(
        DATABASE_URL,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,  # Re-establishes stale connections from Neon suspend
        pool_recycle=300,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# -----------------------------------------------------------------------------
# Database Models
# -----------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id = Column(String(64), primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(255), nullable=False)
    role = Column(String(32), nullable=False, default="user")  # 'admin' | 'user'
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "role": self.role,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class GuestSession(Base):
    __tablename__ = "guest_sessions"

    session_id = Column(String(64), primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class ChatHistory(Base):
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_id = Column(String(64), index=True, nullable=False)
    session_key = Column(String(64), nullable=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    doc_sources = Column(Text, nullable=True)  # JSON-stringified sources list
    model_used = Column(String(128), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "owner_id": self.owner_id,
            "session_key": self.session_key,
            "question": self.question,
            "answer": self.answer,
            "doc_sources": self.doc_sources,
            "model_used": self.model_used,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def init_db():
    """Initializes tables on startup."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency for scoped database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
