from flask import Flask, request, render_template, session, redirect, url_for
import pandas as pd
import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("OPENMETADATA_TOKEN")
groq_key = os.getenv("GROQ_API_KEY")

app = Flask(__name__)
app.secret_key = "metalens-secret-key"

FQN = "ACME_MYSQL.default.FINANCIAL_STAGING.ACCOUNTS"
headers = {"Authorization": f"Bearer {token}"}

def fetch_metadata():
    fqn = session.get("selected_fqn", "ACME_MYSQL.default.FINANCIAL_STAGING.ACCOUNTS")
    response = requests.get(
        f"https://sandbox.open-metadata.org/api/v1/tables/name/{fqn}?fields=columns,tags,owners",
        headers=headers
    )
    data = response.json()
    columns = [
        {"name": col["name"], "type": col["dataType"], "tags": [t["tagFQN"] for t in col.get("tags", [])]}
        for col in data["columns"]
    ]
    return data["name"], columns

def ask_ai(prompt):
    ai_response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
        json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": prompt}], "max_tokens": 1024}
    )
    return ai_response.json()["choices"][0]["message"]["content"]

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        file = request.files["file"]
        df = pd.read_excel(file)
        session["filename"] = file.filename
        session["columns"] = list(df.columns)
        session["rows"] = df.head(5).to_dict(orient="records")
        session["shape"] = list(df.shape)
        profile = {}
        for col in df.columns:
            null_count = int(df[col].isnull().sum())
            profile[col] = {
                "null_count": null_count,
                "unique_values": int(df[col].nunique()),
                "sample": str(df[col].iloc[0])
            }
        session["profile"] = profile
        return redirect(url_for("analysis"))
    return render_template("index.html")

@app.route("/analysis")
def analysis():
    if not session.get("filename"):
        return redirect(url_for("index"))
    table_name, columns = fetch_metadata()
    pii_sensitive = [col["name"] for col in columns if any("PII.Sensitive" in t for t in col["tags"])]
    pii_nonsensitive = [col["name"] for col in columns if any("PII.NonSensitive" in t for t in col["tags"])]
    excel_cols = session.get("columns", [])
    matched = [col for col in excel_cols if col.upper() in [c["name"].upper() for c in columns]]
    unmatched = [col for col in excel_cols if col.upper() not in [c["name"].upper() for c in columns]]

    # PII Masking
    preview_rows = session.get("rows", [])
    masked_rows = []
    for row in preview_rows:
        masked_row = {}
        for key, val in row.items():
            if key.upper() in [p.upper() for p in pii_sensitive]:
                masked_row[key] = "*** MASKED ***"
            else:
                masked_row[key] = val
        masked_rows.append(masked_row)

    return render_template("analysis.html",
        table_name=table_name,
        columns=columns,
        pii_sensitive=pii_sensitive,
        pii_nonsensitive=pii_nonsensitive,
        preview_columns=session.get("columns", []),
        preview_rows=masked_rows,
        matched=matched,
        unmatched=unmatched
    )
@app.route("/quality")
def quality():
    if not session.get("filename"):
        return redirect(url_for("index"))
    table_name, columns = fetch_metadata()
    pii_sensitive = [col["name"] for col in columns if any("PII.Sensitive" in t for t in col["tags"])]
    profile = session.get("profile", {})
    total_nulls = sum(v["null_count"] for v in profile.values())
    pii_penalty = len(pii_sensitive) * 10
    null_penalty = min(total_nulls * 5, 30)
    quality_score = max(100 - pii_penalty - null_penalty, 0)
    return render_template("quality.html",
        quality_score=quality_score,
        profile=profile,
        pii_sensitive=pii_sensitive,
        total_nulls=total_nulls
    )

@app.route("/chat", methods=["GET", "POST"])
def chat():
    if not session.get("filename"):
        return redirect(url_for("index"))
    response = None
    if request.method == "POST":
        question = request.form.get("question")
        table_name, columns = fetch_metadata()
        prompt = f"""
You are a data analyst assistant for MetaLens.
Table: {table_name}
Columns: {json.dumps(columns)}
Excel Data Profile: {json.dumps(session.get("profile", {}))}
User question: {question}
Answer concisely and helpfully.
"""
        response = ask_ai(prompt)
    return render_template("chat.html", response=response)

@app.route("/lineage")
def lineage():
    if not session.get("filename"):
        return redirect(url_for("index"))
    table_name, columns = fetch_metadata()
    lineage_response = requests.get(
        f"https://sandbox.open-metadata.org/api/v1/lineage/table/name/{FQN}?upstreamDepth=1&downstreamDepth=1",
        headers=headers
    )
    lineage_data = lineage_response.json()
    nodes = lineage_data.get("nodes", [])
    upstream = lineage_data.get("upstreamEdges", [])
    downstream = lineage_data.get("downstreamEdges", [])
    return render_template("lineage.html",
        table_name=table_name,
        nodes=nodes,
        upstream=upstream,
        downstream=downstream,
        filename=session.get("filename")
    )

@app.route("/search_tables")
def search_tables():
    query = request.args.get("q", "")
    if not query:
        return {"tables": []}
    response = requests.get(
        f"https://sandbox.open-metadata.org/api/v1/search/query?q={query}&index=table_search_index&limit=10",
        headers=headers
    )
    results = response.json().get("hits", {}).get("hits", [])
    tables = [{"fqn": r["_source"]["fullyQualifiedName"], "name": r["_source"]["name"]} for r in results]
    return {"tables": tables}

@app.route("/select_table", methods=["POST"])
def select_table():
    fqn = request.form.get("fqn")
    session["selected_fqn"] = fqn
    return {"status": "ok"}


@app.route("/reset_table")
def reset_table():
    session.pop("selected_fqn", None)
    return redirect(url_for("index"))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)