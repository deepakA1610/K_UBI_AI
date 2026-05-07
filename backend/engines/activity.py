from datetime import datetime
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.entities import UBID, SourceRecord, Event, UBIDStatus

def update_activity_statuses():
    db: Session = SessionLocal()
    
    # Get all UBIDs
    ubids = db.query(UBID).all()
    now = datetime.utcnow()
    
    for ubid in ubids:
        # Find all events linked to this UBID's source records
        source_records = db.query(SourceRecord).filter(SourceRecord.ubid_id == ubid.id).all()
        record_ids = [r.id for r in source_records]
        
        events = db.query(Event).filter(Event.source_record_id.in_(record_ids)).order_by(Event.event_date.desc()).all()
        
        total_lp = 0
        evidence_trail = {
            "last_calculated": now.isoformat(),
            "factors": []
        }
        
        if not events:
            # No events = 0 LP
            ubid.status = UBIDStatus.CLOSED
            ubid.activity_pulse_score = 0
            evidence_trail["verdict_justification"] = "No activity events recorded across any linked department systems."
        else:
            latest_date = events[0].event_date
            months_since_latest = (now.year - latest_date.year) * 12 + now.month - latest_date.month
            
            # Calculate temporal decay on Life Points
            for event in events:
                # Use days for more accurate month calculation
                delta = now - event.event_date
                months_ago = delta.days // 30
                
                if months_ago <= 4: # Very recent
                    multiplier = 1.0
                elif months_ago <= 12: # Within a year
                    multiplier = 0.6
                elif months_ago <= 24: # Up to 2 years
                    multiplier = 0.2
                else: # Dead
                    multiplier = 0.0
                    
                effective_lp = int(event.life_points * multiplier)
                total_lp += effective_lp
                
                if effective_lp > 0:
                    evidence_trail["factors"].append({
                        "event_type": event.event_type,
                        "date": event.event_date.isoformat(),
                        "base_lp": event.life_points,
                        "temporal_multiplier": multiplier,
                        "effective_lp": effective_lp
                    })

            ubid.activity_pulse_score = total_lp
            
            # Status thresholds (Lowered for better demo differentiation)
            if total_lp >= 30:
                ubid.status = UBIDStatus.ACTIVE
                evidence_trail["verdict_justification"] = f"Recent activity detected ({total_lp} LP). Business is currently operating."
            elif total_lp >= 5:
                ubid.status = UBIDStatus.DORMANT
                evidence_trail["verdict_justification"] = f"Minor activity ({total_lp} LP). Signs of life detected but inconsistent."
            else:
                ubid.status = UBIDStatus.CLOSED
                evidence_trail["verdict_justification"] = f"Negligible pulse ({total_lp} LP). No operational signals detected in the last 12-24 months."
                
        ubid.evidence_trail = evidence_trail
            
    db.commit()
    db.close()
    return {"status": "success", "processed": len(ubids)}

if __name__ == "__main__":
    res = update_activity_statuses()
    print("Activity classification complete:", res)
