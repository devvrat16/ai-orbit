"""Create a Google-Sheets-ready workbook from the public trial dataset."""
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parent
DATA=ROOT/"data"
OUT=DATA/"AI_Signal_Submission.xlsx"

FILES=[
    ("Entities","catalog"),
    ("Relationships","relationships"),
    ("Companies","companies"),
    ("Tools","tools"),
    ("Models","models"),
    ("Repositories","repositories"),
    ("MCP","mcp"),
    ("Research","research_papers"),
    ("News","news"),
    ("Data Quality","validation_report"),
]

def flatten(rows):
    if isinstance(rows, dict):
        return [{"metric":k,"value":json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v} for k,v in rows.items()]
    out=[]
    for x in rows:
        row={}
        for k,v in x.items():
            if k=="source" and isinstance(v,dict):
                row["source_name"]=v.get("name",""); row["source_url"]=v.get("url","")
            elif isinstance(v,(list,dict)):
                row[k]=json.dumps(v,ensure_ascii=False)
            else:
                row[k]=v
        out.append(row)
    return out

with pd.ExcelWriter(OUT,engine="openpyxl") as writer:
    for sheet,file in FILES:
        p=DATA/f"{file}.json"
        rows=json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
        pd.DataFrame(flatten(rows)).to_excel(writer,sheet_name=sheet[:31],index=False)

print(OUT)
