import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, Enum, Float, Integer
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from datetime import datetime
import enum

from app.core.database import Base

class UBIDStatus(enum.Enum):
    ACTIVE = "ACTIVE"
    DORMANT = "DORMANT"
    CLOSED = "CLOSED"

class ReviewStatus(enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"

class UBID(Base):
    __tablename__ = "ubids"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    canonical_name = Column(String, index=True)
    status = Column(Enum(UBIDStatus), default=UBIDStatus.ACTIVE)
    
    # Activity Intelligence
    activity_pulse_score = Column(Integer, default=0)
    evidence_trail = Column(JSONB, default=dict)
    
    anchored_pan = Column(String, index=True, nullable=True)
    anchored_gstin = Column(String, index=True, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    source_records = relationship("SourceRecord", back_populates="ubid")

class SourceRecord(Base):
    __tablename__ = "source_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ubid_id = Column(UUID(as_uuid=True), ForeignKey("ubids.id"), nullable=True)
    department = Column(String, index=True) # e.g., 'Labour', 'Factories', 'BESCOM'
    source_id = Column(String, index=True)  # ID in their system
    
    # Bronze Layer: Raw Ingestion Data
    raw_data = Column(JSONB, default=dict)
    
    # Silver Layer: Extracted & PII-Safe Fields for Splink
    extracted_name = Column(String)
    extracted_address = Column(String)
    extracted_pincode = Column(String)
    phonetic_name = Column(String, index=True) # Double Metaphone
    hashed_pan = Column(String, index=True, nullable=True) # Salted SHA-256
    hashed_gstin = Column(String, index=True, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)

    ubid = relationship("UBID", back_populates="source_records")
    events = relationship("Event", back_populates="source_record")

class Event(Base):
    __tablename__ = "events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_record_id = Column(UUID(as_uuid=True), ForeignKey("source_records.id"))
    event_type = Column(String) # e.g., 'Inspection', 'Renewal', 'Meter Reading'
    event_date = Column(DateTime)
    description = Column(String, nullable=True)
    life_points = Column(Integer, default=0)

    source_record = relationship("SourceRecord", back_populates="events")

class ReviewQueue(Base):
    __tablename__ = "review_queue"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    record_1_id = Column(UUID(as_uuid=True), ForeignKey("source_records.id"))
    record_2_id = Column(UUID(as_uuid=True), ForeignKey("source_records.id"))
    confidence_score = Column(Float)
    status = Column(Enum(ReviewStatus), default=ReviewStatus.PENDING)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    record_1 = relationship("SourceRecord", foreign_keys=[record_1_id])
    record_2 = relationship("SourceRecord", foreign_keys=[record_2_id])

class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    review_queue_id = Column(UUID(as_uuid=True), nullable=True)
    reviewer_id = Column(String)
    decision = Column(String) # "APPROVE_MERGE", "REJECT"
    justification = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)
