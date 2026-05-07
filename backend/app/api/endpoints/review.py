from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.entities import ReviewQueue, ReviewStatus, UBID, SourceRecord, AuditLog
from pydantic import BaseModel, UUID4
from typing import List

router = APIRouter()

class ReviewDecision(BaseModel):
    decision: str # "APPROVE_MERGE", "REJECT"
    justification: str
    reviewer_id: str = "ADMIN_01"

@router.get("/queue")
def get_review_queue(db: Session = Depends(get_db)):
    # Returns items pending review
    queue = db.query(ReviewQueue).filter(ReviewQueue.status == ReviewStatus.PENDING).all()
    # Eager load relationships for simplicity in prototype
    results = []
    for item in queue:
        r1 = db.query(SourceRecord).get(item.record_1_id)
        r2 = db.query(SourceRecord).get(item.record_2_id)
        results.append({
            "id": item.id,
            "record_1": r1,
            "record_2": r2,
            "confidence_score": item.confidence_score,
            "status": item.status
        })
    return results

@router.post("/queue/{review_id}")
def process_review_decision(review_id: UUID4, decision_data: ReviewDecision, db: Session = Depends(get_db)):
    item = db.query(ReviewQueue).get(review_id)
    if not item:
        raise HTTPException(status_code=404, detail="Review item not found")
        
    r1 = db.query(SourceRecord).get(item.record_1_id)
    r2 = db.query(SourceRecord).get(item.record_2_id)
        
    if decision_data.decision == "APPROVE_MERGE":
        # Merge them into the same UBID
        if r1.ubid_id:
            r2.ubid_id = r1.ubid_id
        elif r2.ubid_id:
            r1.ubid_id = r2.ubid_id
        else:
            new_ubid = UBID(canonical_name=r1.extracted_name)
            db.add(new_ubid)
            db.flush()
            r1.ubid_id = new_ubid.id
            r2.ubid_id = new_ubid.id
            
        item.status = ReviewStatus.APPROVED
        
    elif decision_data.decision == "REJECT":
        # Keep them separate, assign new UBIDs if they don't have one
        if not r1.ubid_id:
            u1 = UBID(canonical_name=r1.extracted_name)
            db.add(u1)
            db.flush()
            r1.ubid_id = u1.id
        if not r2.ubid_id:
            u2 = UBID(canonical_name=r2.extracted_name)
            db.add(u2)
            db.flush()
            r2.ubid_id = u2.id
            
        item.status = ReviewStatus.REJECTED
        
    # LOG AUDIT RECORD
    audit = AuditLog(
        review_queue_id=item.id,
        reviewer_id=decision_data.reviewer_id,
        decision=decision_data.decision,
        justification=decision_data.justification
    )
    db.add(audit)
    db.commit()
    return {"status": "success"}
