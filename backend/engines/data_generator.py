import random
import uuid
import json
from datetime import datetime, timedelta
from app.core.database import SessionLocal, engine, Base
from app.models.entities import SourceRecord, Event, UBID, ReviewQueue
from engines.security import hash_pii, phonetic_encode
import pandas as pd
import os

# Use a relative path for deployment
DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "companies_subset.csv")

# We need to recreate tables first since we changed schema
Base.metadata.create_all(bind=engine)

def random_date(start_days_ago=1000, end_days_ago=0):
    now = datetime.utcnow()
    # Ensure start is older than end
    if start_days_ago < end_days_ago:
        start_days_ago, end_days_ago = end_days_ago, start_days_ago
    return now - timedelta(days=random.randint(end_days_ago, start_days_ago))

def random_pan():
    return f"ABCDE{random.randint(1000, 9999)}F"

def random_gstin(pan):
    return f"29{pan}1Z5"

# Complex Edge Cases Scenarios
def generate_parent_subsidiary(db, base_pan):
    """Same PAN, Different GSTIN, Same Address"""
    address = {"street": "Tech Park Main Road", "city": "Bengaluru", "district": "Bangalore Urban", "pincode": "560100"}
    
    # Parent - Commercial Taxes
    r1 = SourceRecord(
        department="Commercial Taxes",
        source_id=f"CT-{uuid.uuid4().hex[:6]}",
        raw_data={
            "legal_name": "Apex Holdings Ltd",
            "trade_name": "Apex Group",
            "gstin": random_gstin(base_pan),
            "pan": base_pan,
            "principal_place_of_business": address
        },
        extracted_name="Apex Holdings Ltd",
        extracted_address="Tech Park Main Road Bengaluru",
        extracted_pincode="560100",
        phonetic_name=phonetic_encode("Apex Holdings Ltd"),
        hashed_pan=hash_pii(base_pan),
        hashed_gstin=hash_pii(random_gstin(base_pan))
    )
    db.add(r1)
    
    # Subsidiary - Factories
    r2 = SourceRecord(
        department="Factories",
        source_id=f"FAC-{uuid.uuid4().hex[:6]}",
        raw_data={
            "factory_name": "Apex Manufacturing Sub",
            "occupier_name": "John Doe",
            "location": address,
            "license_no": "LIC999"
        },
        extracted_name="Apex Manufacturing Sub",
        extracted_address="Tech Park Main Road Bengaluru",
        extracted_pincode="560100",
        phonetic_name=phonetic_encode("Apex Manufacturing Sub"),
        hashed_pan=hash_pii(base_pan) # Inherited PAN theoretically, though missing from raw
    )
    db.add(r2)
    return [r1, r2]

def generate_franchise(db, name):
    """Same Name, Different Owners, Different PANs, Different Locations"""
    records = []
    for i in range(2):
        pan = random_pan()
        r = SourceRecord(
            department="Labour",
            source_id=f"LAB-{uuid.uuid4().hex[:6]}",
            raw_data={
                "establishment_name": name,
                "owner_name": f"Owner {i}",
                "full_address": f"Location {i} Street",
                "pincode": f"56000{i}"
            },
            extracted_name=name,
            extracted_address=f"Location {i} Street",
            extracted_pincode=f"56000{i}",
            phonetic_name=phonetic_encode(name),
            hashed_pan=hash_pii(pan)
        )
        db.add(r)
        records.append(r)
    return records

def generate_mock_data():
    db = SessionLocal()
    
    # 1. Database Flush
    if db.query(SourceRecord).count() > 0:
        db.execute(ReviewQueue.__table__.delete())
        db.execute(Event.__table__.delete())
        db.execute(SourceRecord.__table__.delete())
        db.execute(UBID.__table__.delete())
        db.commit()

    if not os.path.exists(DATA_PATH):
        return {"status": "error", "message": "Portable dataset not found in data/ folder."}

    # 2. Load Karnataka Sample
    # We load 2000 records as base "Truth" to generate variations from
    try:
        df_kar = pd.read_csv(DATA_PATH, low_memory=False)
        # We take a sample of 1000 for the actual generation process
        if len(df_kar) > 1000:
            df_kar = df_kar.sample(n=1000, random_state=42)
    except Exception as e:
        return {"status": "error", "message": f"Failed to read dataset: {str(e)}"}

    all_records = []
    
    # Status Mapping (ROC -> K-UBI)
    STATUS_MAP = {
        "ACTV": "ACTIVE", "DRMT": "DORMANT", "D455": "DORMANT",
        "STOF": "CLOSED", "DISD": "CLOSED", "LIQD": "CLOSED",
        "AMAL": "CLOSED", "ULQD": "DORMANT"
    }

    # 3. Process ROC Records into Medallion Bronze Layer
    # Replace NaNs with None to avoid JSON serialization errors (NaN is not valid JSON)
    df_kar = df_kar.where(pd.notnull(df_kar), None)
    
    for _, row in df_kar.iterrows():
        base_name = str(row['COMPANY_NAME'])
        cin = str(row['CORPORATE_IDENTIFICATION_NUMBER'])
        address = str(row['REGISTERED_OFFICE_ADDRESS'])
        
        # Inject realistic noise for entity resolution demo
        # For each record, we'll create 1.2 records on average (some duplicates with noise)
        variants = [base_name]
        if random.random() > 0.7:
            # Create a typo or fragment variant
            if len(base_name) > 10:
                variant = base_name[:random.randint(8, len(base_name)-2)] + " LTD"
                variants.append(variant)

        for name_variant in variants:
            # Randomly drop some fields to simulate siloed data
            has_pan = random.random() > 0.4
            pan = f"ABCDE{random.randint(1000, 9999)}F" if has_pan else None
            
            # Map ROC schema to our Bronze schema with safe NaN handling
            safe_raw_data = {k: (None if pd.isna(v) else v) for k, v in row.to_dict().items()}
            
            r = SourceRecord(
                department=random.choice(["Commercial Taxes", "Labour", "Factories", "BESCOM", "KSPCB"]),
                source_id=f"ROC-{cin[:6]}",
                raw_data=safe_raw_data, # Store full ROC JSONB safely
                extracted_name=name_variant,
                extracted_address=address[:100],
                extracted_pincode=address[-6:] if address[-6:].isdigit() else "560001",
                phonetic_name=phonetic_encode(name_variant),
                hashed_pan=hash_pii(pan) if pan else None
            )
            db.add(r)
            all_records.append(r)
            
            # 4. Generate Events based on ROC status
            roc_status = str(row['COMPANY_STATUS'])
            # Force at least 75% to be ACTIVE for a better demo experience
            if random.random() < 0.75:
                mapped_status = "ACTIVE"
            else:
                mapped_status = STATUS_MAP.get(roc_status, "ACTIVE")
            
            event_pool = [
                ("GST Return", "Monthly GSTR-3B filing confirmed."),
                ("Tax Payment", "Advance tax installment processed."),
                ("Annual Filing", "MCA Form MGT-7 submitted."),
                ("Labour Compliance", "Employee registry update verified."),
                ("Utility Payment", "BESCOM/BWSSB bill cleared."),
                ("Trade License", "BBMP Trade License renewal."),
                ("Inspection", "On-site safety audit completed."),
                ("PF Deposit", "EPFO monthly contribution confirmed.")
            ]

            if mapped_status == "ACTIVE":
                # High-frequency activity signals
                num_events = random.randint(8, 20)
                for _ in range(num_events):
                    e_type, e_desc = random.choice(event_pool)
                    db.add(Event(
                        source_record_id=r.id,
                        event_type=e_type,
                        description=e_desc,
                        event_date=random_date(180), # Last 6 months
                        life_points=random.randint(15, 45) 
                    ))
            elif mapped_status == "DORMANT":
                # Low-frequency, older signals
                num_events = random.randint(2, 5)
                for _ in range(num_events):
                    e_type, e_desc = random.choice(event_pool)
                    db.add(Event(
                        source_record_id=r.id,
                        event_type=e_type,
                        description=f"Occasional {e_desc.lower()}",
                        event_date=random_date(600, 200),
                        life_points=random.randint(5, 12)
                    ))
            else: # CLOSED
                # Residual old signals only
                if random.random() > 0.7:
                    db.add(Event(
                        source_record_id=r.id,
                        event_type="Terminal Filing",
                        description="Business closure notification filed.",
                        event_date=random_date(1500, 800),
                        life_points=5
                    ))

    db.commit()
    db.close()
    return {"status": "success", "records_created": len(all_records), "source": "Kaggle ROC Dataset", "events_created": "Massive"}

if __name__ == "__main__":
    generate_mock_data()
    print("Substantive mock data generated.")
