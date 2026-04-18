import requests
import pandas as pd
import json
from dotenv import load_dotenv
import os

load_dotenv()
token = os.getenv("OPENMETADATA_TOKEN")
groq_key = os.getenv("GROQ_API_KEY")

headers = {"Authorization": f"Bearer {token}"}
FQN = "ACME_MYSQL.default.FINANCIAL_STAGING.ACCOUNTS"
# --- Step 1: Fetch metadata ---
response = requests.get(
    f"https://sandbox.open-metadata.org/api/v1/tables/name/{FQN}?fields=columns,tags,owners",
    headers=headers
)
data = response.json()
columns = [
    {"name": col["name"], "type": col["dataType"], "tags": [t["tagFQN"] for t in col.get("tags", [])]}
    for col in data["columns"]
]

# --- Step 2: Fetch lineage ---
lineage_response = requests.get(
    f"https://sandbox.open-metadata.org/api/v1/lineage/table/{data['id']}?upstreamDepth=1&downstreamDepth=1",
    headers=headers
)
lineage_data = lineage_response.json()
nodes = {n["id"]: n["fullyQualifiedName"] for n in lineage_data.get("nodes", [])}
downstream = [nodes.get(e.get("toEntity", ""), e.get("toEntity", "")) for e in lineage_data.get("downstreamEdges", [])]
upstream = [nodes.get(e.get("fromEntity", ""), e.get("fromEntity", "")) for e in lineage_data.get("upstreamEdges", [])]

print("Upstream:", upstream)
print("Downstream:", downstream)

# --- Step 3: Parse Excel ---
df = pd.read_excel("sample_data.xlsx")
sample_rows = df.head(3).to_dict(orient="records")

# --- Step 4: Profile data ---
profile = {}
for col in df.columns:
    profile[col] = {
        "null_count": int(df[col].isnull().sum()),
        "unique_values": int(df[col].nunique()),
        "sample": str(df[col].iloc[0])
    }
    if df[col].dtype in ["int64", "float64"]:
        profile[col]["min"] = float(df[col].min())
        profile[col]["max"] = float(df[col].max())

# --- Step 5: Build prompt ---
prompt = f"""
You are a data analyst. Given the following table metadata, sample data, column profiles, and lineage, explain:
1. What this dataset is about
2. Which columns are sensitive (PII)
3. What might break if a column is deleted (use lineage to be specific)

Table: {data['name']}
Upstream: {upstream}
Downstream: {downstream}
Columns: {json.dumps(columns, indent=2)}
Sample Data: {json.dumps(sample_rows, indent=2)}
Data Profile: {json.dumps(profile, indent=2)}
"""

# --- Step 6: Send to Groq ---
ai_response = requests.post(
    "https://api.groq.com/openai/v1/chat/completions",
    headers={
        "Authorization": f"Bearer {groq_key}",
        "Content-Type": "application/json"
    },
    json={
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1024
    }
)

result = ai_response.json()
print(result["choices"][0]["message"]["content"])