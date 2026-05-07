import pandas as pd
import os

# Local cache path from your machine
KAGGLE_PATH = r"C:\Users\arund\.cache\kagglehub\datasets\rowhitswami\all-indian-companies-registration-data-1900-2019\versions\2\registered_companies.csv"
# Portable path for deployment
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "data")
OUTPUT_PATH = os.path.join(OUTPUT_DIR, "companies_subset.csv")

def extract_subset():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    if os.path.exists(KAGGLE_PATH):
        print(f"Reading source data from {KAGGLE_PATH}...")
        try:
            # We only need a subset for the demo to keep the repo/deployment light
            df = pd.read_csv(KAGGLE_PATH, low_memory=False)
            print("Filtering Karnataka records...")
            df_kar = df[df['REGISTERED_STATE'] == 'Karnataka']
            
            # Take a 5000 record sample
            sample_size = min(5000, len(df_kar))
            df_subset = df_kar.sample(n=sample_size, random_state=42)
            
            df_subset.to_csv(OUTPUT_PATH, index=False)
            print(f"Successfully created portable dataset: {OUTPUT_PATH} ({sample_size} records)")
        except Exception as e:
            print(f"Error during extraction: {e}")
    else:
        print("Kaggle source not found. If you are already on the server, ensure data/companies_subset.csv exists.")

if __name__ == "__main__":
    extract_subset()
