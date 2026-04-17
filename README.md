# MetaLens
MetaLens — Excel + AI + OpenMetadata Assistant
> Upload an Excel file → AI explains your data, flags PII, and shows what breaks if you modify it.

Built for the **WeMakeDevs x OpenMetadata Hackathon (Apr 17–26, 2026)**

**##Problem**
Data teams work with Excel files daily but have no easy way to:
- Know which columns contain sensitive (PII) data
- Understand what downstream pipelines depend on a column
- Get a plain-English explanation of what the data means
  
****##Solution**
MetaLens connects your Excel file to OpenMetadata's governance layer and uses AI to:
- **Flag PII columns** automatically
- **Show lineage** — what breaks if you delete/modify a column
- **Answer questions** about your data in plain English


**##  Core Flow**
Upload Excel → Parse columns (pandas) → Query OpenMetadata API → Combine context → Send to AI → Show results


**## Tech Stack**
| Layer | Tech |
| Backend | Python, Flask |
| Excel Parsing | pandas, openpyxl |
| Metadata | OpenMetadata REST API |
| AI | API |
| Frontend | HTML + Flask (or React) |


**##  Features**
-  PII auto-detection + warnings
-  "What breaks if I delete this column?" impact analysis
-  Lineage visualization
-  Chat Q&A with your data
-  Data quality score

**## Getting Started**
*Setup instructions coming soon*

**## Project Structure**
*To be updated as files are added*

  
