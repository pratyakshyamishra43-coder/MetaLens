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
    columns = []
    for col in data["columns"]:
        tags = [t["tagFQN"] for t in col.get("tags", [])]
        sensitivity = next((t.split(".")[-1] for t in tags if "DataSensitivity" in t), None)
        tier = next((t.split(".")[-1] for t in tags if "DataTier" in t), None)
        columns.append({
            "name": col["name"],
            "type": col["dataType"],
            "tags": tags,
            "sensitivity": sensitivity,
            "tier": tier,
            "description": col.get("description", "")
        })
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
        prompt = f"""You are a data analyst assistant for MetaLens.
Table: {table_name}
Columns: {json.dumps(columns)}
Excel Data Profile: {json.dumps(session.get("profile", {}))}
User question: {question}
Answer concisely and helpfully."""
        response = ask_ai(prompt)
    return render_template("chat.html", 
        response=response,
        preview_columns=session.get("columns", [])
    )

@app.route("/lineage")
def lineage():
    if not session.get("filename"):
        return redirect(url_for("index"))
    table_name, columns = fetch_metadata()
    fqn = session.get("selected_fqn", "ACME_MYSQL.default.FINANCIAL_STAGING.ACCOUNTS")
    
    lineage_response = requests.get(
        f"https://sandbox.open-metadata.org/api/v1/lineage/table/name/{fqn}?upstreamDepth=1&downstreamDepth=1",
        headers=headers
    )
    lineage_data = lineage_response.json()
    nodes = lineage_data.get("nodes", [])
    upstream = lineage_data.get("upstreamEdges", [])
    downstream = lineage_data.get("downstreamEdges", [])

    # Column-level lineage
    col_lineage = []
    for edge in upstream + downstream:
        cols = edge.get("columns", [])
        if cols:
            col_lineage.append({
                "from": edge.get("fromEntity", {}).get("fqn", "Unknown"),
                "to": edge.get("toEntity", {}).get("fqn", "Unknown"),
                "columns": cols
            })

    return render_template("lineage.html",
        table_name=table_name,
        columns=columns,
        nodes=nodes,
        upstream=upstream,
        downstream=downstream,
        col_lineage=col_lineage,
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

@app.route("/impact", methods=["POST"])
def impact():
    column = request.form.get("column")
    table_name, columns = fetch_metadata()
    col_meta = next((c for c in columns if c["name"].upper() == column.upper()), None)
    tags = col_meta["tags"] if col_meta else []
    is_pii = any("PII.Sensitive" in t for t in tags)

    prompt = f"""You are a data governance expert.
Table: {table_name}
Column being deleted: {column}
Column metadata: {col_meta}
All columns: {[c['name'] for c in columns]}
PII Sensitive: {is_pii}

Answer these 4 things concisely:
1. What downstream processes or reports likely depend on this column?
2. What data quality issues will arise if this column is removed?
3. What compliance/PII risks exist?
4. Your recommendation: should this column be deleted, masked, or kept?

Also give an impact score from 1-10 (10 = most critical).
End your response with exactly this line: IMPACT_SCORE: X"""

    ai_response = ask_ai(prompt)
    
    # Extract score
    score = 5
    for line in ai_response.split('\n'):
        if 'IMPACT_SCORE:' in line:
            try:
                score = int(line.split(':')[1].strip())
            except:
                score = 5
            ai_response = ai_response.replace(line, '').strip()
            break

    return {"analysis": ai_response, "score": score}

@app.route("/column_scores")
def column_scores():
    table_name, columns = fetch_metadata()
    profile = session.get("profile", {})
    scores = {}
    for col in columns:
        score = 5  # base
        tags = col["tags"]
        name = col["name"].upper()
        if any("PII.Sensitive" in t for t in tags): score += 3
        if any("PII.NonSensitive" in t for t in tags): score += 1
        if any(k in name for k in ["ID", "NUMBER", "ACCOUNT", "TAX", "SSN", "BALANCE"]): score += 1
        if col["type"] in ["DECIMAL", "NUMERIC", "FLOAT", "DOUBLE"]: score += 1
        null_count = profile.get(col["name"], {}).get("null_count", 0)
        if null_count == 0: score += 1
        scores[col["name"]] = min(score, 10)
    return {"scores": scores}



    # ── Task 8: Metadata Completeness Checker ──────────────────────────────────
@app.route("/completeness")
def completeness():
    if not session.get("filename"):
        return redirect(url_for("index"))
    table_name, columns = fetch_metadata()

    # Fetch raw data to check descriptions
    fqn = session.get("selected_fqn", "ACME_MYSQL.default.FINANCIAL_STAGING.ACCOUNTS")
    raw = requests.get(
        f"https://sandbox.open-metadata.org/api/v1/tables/name/{fqn}?fields=columns,tags,owners,description",
        headers=headers
    ).json()

    col_scores = []
    for col in raw["columns"]:
        score = 0
        checks = {}

        checks["has_description"] = bool(col.get("description"))
        checks["has_tags"] = len(col.get("tags", [])) > 0
        checks["has_data_type"] = bool(col.get("dataType"))
        checks["has_sensitivity"] = any("DataSensitivity" in t["tagFQN"] for t in col.get("tags", []))

        score = sum(checks.values()) * 25  # 0, 25, 50, 75, or 100

        col_scores.append({
            "name": col["name"],
            "score": score,
            "checks": checks,
            "tags": [t["tagFQN"] for t in col.get("tags", [])]
        })

    table_completeness = round(sum(c["score"] for c in col_scores) / len(col_scores)) if col_scores else 0
    table_description = raw.get("description", "")

    return render_template("completeness.html",
        table_name=table_name,
        col_scores=col_scores,
        table_completeness=table_completeness,
        table_description=table_description
    )


# ── Task 9: Smart Table Matcher ────────────────────────────────────────────
@app.route("/smart_match")
def smart_match():
    if not session.get("filename"):
        return redirect(url_for("index"))

    table_name, columns = fetch_metadata()
    excel_cols = session.get("columns", [])
    meta_col_names = [c["name"] for c in columns]

    def similarity(a, b):
        a, b = a.upper().replace("_", ""), b.upper().replace("_", "")
        if a == b: return 100
        if a in b or b in a: return 80
        # character overlap score
        common = sum(1 for ch in a if ch in b)
        return round((common / max(len(a), len(b))) * 60)

    matches = []
    unmatched_excel = []

    for ecol in excel_cols:
        best_match = None
        best_score = 0
        for mcol in columns:
            s = similarity(ecol, mcol["name"])
            if s > best_score:
                best_score = s
                best_match = mcol
        if best_score >= 60:
            matches.append({
                "excel_col": ecol,
                "meta_col": best_match["name"],
                "score": best_score,
                "tags": best_match["tags"],
                "type": best_match["type"],
                "confidence": "High" if best_score >= 80 else "Medium"
            })
        else:
            unmatched_excel.append(ecol)

    # AI suggestions for unmatched columns
    ai_suggestions = {}
    if unmatched_excel:
        prompt = f"""You are a data mapping expert.
Excel columns with no match in the metadata table: {unmatched_excel}
Available OpenMetadata columns: {meta_col_names}

For each unmatched Excel column, suggest the closest OpenMetadata column it might correspond to, or say "No match" if none fits.
Respond ONLY as JSON like: {{"EXCEL_COL": "META_COL or No match"}}
No explanation, no markdown."""
        try:
            raw_ai = ask_ai(prompt)
            raw_ai = raw_ai.replace("```json", "").replace("```", "").strip()
            ai_suggestions = json.loads(raw_ai)
        except:
            ai_suggestions = {col: "Could not determine" for col in unmatched_excel}

    return render_template("smart_match.html",
        table_name=table_name,
        matches=matches,
        unmatched_excel=unmatched_excel,
        ai_suggestions=ai_suggestions,
        excel_cols=excel_cols,
        meta_col_names=meta_col_names
    )


from flask import send_file
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.units import cm
import io

@app.route("/export_pdf")
def export_pdf():
    if not session.get("filename"):
        return redirect(url_for("index"))

    table_name, columns = fetch_metadata()
    profile = session.get("profile", {})
    filename = session.get("filename", "report")

    # PII counts
    pii_sensitive = [c for c in columns if any("PII.Sensitive" in t for t in c["tags"])]
    pii_nonsensitive = [c for c in columns if any("PII.NonSensitive" in t for t in c["tags"])]

    # Quality score (same logic as /quality)
    total_nulls = sum(v["null_count"] for v in profile.values())
    pii_penalty = len(pii_sensitive) * 10
    null_penalty = min(total_nulls * 5, 30)
    quality_score = max(100 - pii_penalty - null_penalty, 0)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)

    styles = getSampleStyleSheet()
    accent = colors.HexColor("#6366f1")

    title_style = ParagraphStyle("title", parent=styles["Title"],
                                  textColor=accent, fontSize=22, spaceAfter=6)
    h2_style = ParagraphStyle("h2", parent=styles["Heading2"],
                               textColor=accent, fontSize=13, spaceBefore=16, spaceAfter=6)
    normal = styles["Normal"]

    story = []

    # Header
    story.append(Paragraph("MetaLens — Data Report", title_style))
    story.append(Paragraph(f"Table: <b>{table_name}</b> &nbsp;|&nbsp; File: <b>{filename}</b>", normal))
    story.append(Spacer(1, 0.4*cm))

    # Summary stats
    story.append(Paragraph("Summary", h2_style))
    summary_data = [
        ["Metric", "Value"],
        ["Total Columns (Metadata)", str(len(columns))],
        ["Total Columns (Excel)", str(len(session.get("columns", [])))],
        ["PII Sensitive Columns", str(len(pii_sensitive))],
        ["PII Non-Sensitive Columns", str(len(pii_nonsensitive))],
        ["Total Null Values", str(total_nulls)],
        ["Data Quality Score", f"{quality_score} / 100"],
    ]
    summary_table = Table(summary_data, colWidths=[9*cm, 7*cm])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), accent),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 10),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.HexColor("#f5f3ff"), colors.white]),
        ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#e5e7eb")),
        ("PADDING", (0,0), (-1,-1), 6),
    ]))
    story.append(summary_table)

    # PII Section
    story.append(Paragraph("PII Detection", h2_style))
    if pii_sensitive:
        story.append(Paragraph("<b>Sensitive columns (masked in preview):</b>", normal))
        for c in pii_sensitive:
            story.append(Paragraph(f"• {c['name']} ({c['type']})", normal))
    if pii_nonsensitive:
        story.append(Spacer(1, 0.2*cm))
        story.append(Paragraph("<b>Non-Sensitive PII columns:</b>", normal))
        for c in pii_nonsensitive:
            story.append(Paragraph(f"• {c['name']} ({c['type']})", normal))

    # Column metadata table
    story.append(Paragraph("Column Metadata", h2_style))
    col_data = [["Column Name", "Type", "Tags"]]
    for c in columns:
        tag_str = ", ".join(t.split(".")[-1] for t in c["tags"]) or "—"
        col_data.append([c["name"], c["type"], tag_str])

    col_table = Table(col_data, colWidths=[6*cm, 4*cm, 7*cm])
    col_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), accent),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.HexColor("#f5f3ff"), colors.white]),
        ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#e5e7eb")),
        ("PADDING", (0,0), (-1,-1), 5),
    ]))
    story.append(col_table)

    # Excel profile
    if profile:
        story.append(Paragraph("Excel Data Profile", h2_style))
        prof_data = [["Column", "Nulls", "Unique Values", "Sample"]]
        for col_name, stats in profile.items():
            prof_data.append([
                col_name,
                str(stats.get("null_count", 0)),
                str(stats.get("unique_values", 0)),
                str(stats.get("sample", ""))[:40]
            ])
        prof_table = Table(prof_data, colWidths=[5*cm, 2.5*cm, 3.5*cm, 6*cm])
        prof_table.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), accent),
            ("TEXTCOLOR", (0,0), (-1,0), colors.white),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE", (0,0), (-1,-1), 8),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.HexColor("#f5f3ff"), colors.white]),
            ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#e5e7eb")),
            ("PADDING", (0,0), (-1,-1), 4),
        ]))
        story.append(prof_table)

    doc.build(story)
    buffer.seek(0)

    return send_file(buffer, as_attachment=True,
                     download_name=f"metalens_{table_name}_report.pdf",
                     mimetype="application/pdf")

@app.route("/update_description", methods=["POST"])
def update_description():
    col_name = request.form.get("column")
    description = request.form.get("description")
    fqn = session.get("selected_fqn", "ACME_MYSQL.default.FINANCIAL_STAGING.ACCOUNTS")

    # Fetch current table data to get column id
    table_resp = requests.get(
        f"https://sandbox.open-metadata.org/api/v1/tables/name/{fqn}?fields=columns",
        headers=headers
    ).json()

    # Build patch payload
    columns_patch = []
    for col in table_resp["columns"]:
        if col["name"].upper() == col_name.upper():
            col["description"] = description
        columns_patch.append(col)

    patch_resp = requests.patch(
        f"https://sandbox.open-metadata.org/api/v1/tables/{table_resp['id']}",
        headers={**headers, "Content-Type": "application/json-patch+json"},
        json=[{"op": "replace", "path": "/columns", "value": columns_patch}]
    )



    @app.route("/compliance")
    def compliance():
        if not session.get("filename"):
            return redirect(url_for("index"))
    
    table_name, columns = fetch_metadata()
    
    gdpr_rules = ["ACCOUNT_NUMBER", "EMAIL", "PHONE", "ADDRESS", "NAME", "DOB", "SSN", "IP"]
    hipaa_rules = ["DIAGNOSIS", "MEDICATION", "TREATMENT", "PATIENT", "HEALTH", "INSURANCE", "PROVIDER"]
    pci_rules = ["CARD", "CVV", "EXPIRY", "PAN", "ACCOUNT_NUMBER", "ROUTING", "BALANCE"]

    results = []
    for col in columns:
        name_upper = col["name"].upper()
        tags = col["tags"]
        is_pii_sensitive = any("PII.Sensitive" in t for t in tags)
        is_pii_non = any("PII.NonSensitive" in t for t in tags)

        gdpr_hit = any(r in name_upper for r in gdpr_rules) or is_pii_sensitive
        hipaa_hit = any(r in name_upper for r in hipaa_rules) or is_pii_sensitive
        pci_hit = any(r in name_upper for r in pci_rules)

        risk = "High" if is_pii_sensitive else "Medium" if is_pii_non else "Low"
        risk_color = "#ef4444" if risk == "High" else "#f59e0b" if risk == "Medium" else "#22c55e"

        results.append({
            "name": col["name"],
            "type": col["type"],
            "gdpr": gdpr_hit,
            "hipaa": hipaa_hit,
            "pci": pci_hit,
            "risk": risk,
            "risk_color": risk_color,
            "tags": tags
        })

    gdpr_count = sum(1 for r in results if r["gdpr"])
    hipaa_count = sum(1 for r in results if r["hipaa"])
    pci_count = sum(1 for r in results if r["pci"])
    high_risk = sum(1 for r in results if r["risk"] == "High")

    return render_template("compliance.html",
        table_name=table_name,
        results=results,
        gdpr_count=gdpr_count,
        hipaa_count=hipaa_count,
        pci_count=pci_count,
        high_risk=high_risk
    )

    if patch_resp.status_code in [200, 201]:
             return {"status": "ok"}
    elif patch_resp.status_code == 403:
            return {"status": "error", "detail": "Sandbox is read-only for this account. Write-back works on self-hosted OpenMetadata."}, 200
    else:
            return {"status": "error", "detail": patch_resp.text}, 400

    
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)