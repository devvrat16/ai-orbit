"""Export the SQLite source of truth + auxiliary entity JSON into the canonical AI Orbit schema."""
from __future__ import annotations
import json, re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid5, NAMESPACE_URL
from config import DATA_DIR, FRESHNESS_HOURS
from src.storage import Storage

AUXILIARY = ["mcp","tasks","robots","devices","collections","personal","creative","recent"]

def stable_id(entity_type: str, url: str="", name: str="") -> str:
    key=f"{entity_type.lower()}::{(url or name).strip().lower()}"
    return str(uuid5(NAMESPACE_URL,key))

def clean_text(x):
    return re.sub(r"\s+"," ",str(x or "")).strip()

def canonical_record(record):
    rt=record["record_type"]
    c=record["content"] or {}
    src={"name":record.get("source_name",""),"url":record.get("source_url","")}
    if rt=="STARTUP":
        name=c.get("entityName") or c.get("name") or ""
        return {
            "id":stable_id("COMPANY",src["url"],name),"entity_type":"COMPANY","name":name,
            "description":clean_text(c.get("description")),"url":c.get("website") or src["url"],
            "categories":[x.strip() for x in str(c.get("industry") or "AI").split(",") if x.strip()],
            "source":src,"collected_at":record.get("collected_at"),
            "founding_year":c.get("founded_year"),"industry_sector":c.get("industry"),
            "headquarters":c.get("location"),"employee_count":c.get("employeeCount")
        }
    if rt=="PRODUCT":
        name=c.get("productName") or c.get("startupName") or ""
        cats=[x.strip() for x in str(c.get("category") or "AI Tool").split(",") if x.strip()]
        return {
            "id":stable_id("PRODUCT",src["url"],name),"entity_type":"PRODUCT","name":name,
            "description":clean_text(c.get("description")),"url":c.get("website") or src["url"],
            "categories":cats,"source":src,"collected_at":record.get("collected_at"),
            "startup_name":c.get("startupName"),"pricing_model":c.get("pricingModel")
        }
    if rt=="RESEARCH_PAPER":
        title=c.get("title") or ""
        return {
            "id":stable_id("RESEARCH_PAPER",c.get("paper_url") or src["url"],title),
            "entity_type":"RESEARCH_PAPER","name":title,"description":clean_text(c.get("abstract")),
            "url":c.get("paper_url") or src["url"],"categories":["Research"],
            "source":src,"collected_at":record.get("collected_at"),
            "title":title,"authors":c.get("authors") or [],
            "paper_url":c.get("paper_url") or src["url"],"github_url":c.get("github_url"),
            "github_stars":c.get("github_stars"),"published_date":c.get("published_date")
        }
    if rt=="MODEL":
        name=c.get("modelName") or c.get("name") or ""
        return {"id":stable_id("MODEL",src["url"],name),"entity_type":"MODEL","name":name,"description":clean_text(c.get("description")),"url":c.get("website") or src["url"],"categories":[c.get("category") or "AI/ML"],"source":src,"collected_at":record.get("collected_at"),"license":c.get("license"),"modalities":c.get("modalities") or c.get("tags") or [],"provider":c.get("provider"),"downloads":c.get("downloads"),"likes":c.get("likes"),"last_modified":c.get("last_modified")}
    if rt=="DATASET":
        name=c.get("datasetName") or c.get("name") or ""
        return {"id":stable_id("DATASET",src["url"],name),"entity_type":"DATASET","name":name,"description":clean_text(c.get("description")),"url":c.get("website") or src["url"],"categories":[c.get("category") or "AI Dataset"],"source":src,"collected_at":record.get("collected_at"),"provider":c.get("provider"),"downloads":c.get("downloads"),"likes":c.get("likes"),"last_modified":c.get("last_modified"),"tags":c.get("tags") or []}
    if rt=="REPOSITORY":
        name=c.get("name") or ""
        return {"id":stable_id("REPOSITORY",src["url"],name),"entity_type":"REPOSITORY","name":name,"description":clean_text(c.get("description")),"url":c.get("website") or src["url"],"categories":c.get("categories") or ["Repository"],"source":src,"collected_at":record.get("collected_at"),"stars":c.get("stars"),"primary_language":c.get("primary_language"),"last_updated":c.get("last_updated"),"owner":c.get("owner"),"license":c.get("license"),"topics":c.get("topics") or []}
    if rt=="VIDEO":
        name=c.get("title") or ""
        return {"id":stable_id("VIDEO",src["url"],name),"entity_type":"VIDEO","name":name,"description":clean_text(c.get("description")),"url":c.get("website") or src["url"],"categories":[c.get("category") or "AI Video"],"source":src,"collected_at":record.get("collected_at"),"channel":c.get("channel"),"published_at":c.get("published_at"),"thumbnail":c.get("thumbnail"),"query":c.get("query")}
    if rt=="NEWS":
        name=c.get("title") or ""
        return {
            "id":stable_id("NEWS",src["url"],name),"entity_type":"NEWS","name":name,
            "description":clean_text(c.get("summary") or c.get("full_text")),
            "url":src["url"],"categories":[c.get("category") or "AI News"],"source":src,
            "collected_at":record.get("collected_at"),"published_at":c.get("date"),
            "author":c.get("author"),"summary":c.get("summary")
        }
    if rt=="JOB":
        name=c.get("title") or ""
        return {
            "id":stable_id("JOB",src["url"],name),"entity_type":"JOB","name":name,
            "description":f"{c.get('company','')} · {c.get('role_family','Other')}",
            "url":c.get("url") or src["url"],"categories":[c.get("role_family") or "Other"],
            "source":src,"collected_at":record.get("collected_at"),
            "company":c.get("company"),"date":c.get("date"),"is_remote":c.get("is_remote",False),
            "role_family":c.get("role_family"),"location":c.get("location")
        }
    return None

def is_fresh(record):
    value=record.get("published_at") or record.get("date")
    if not value: return False
    try:
        dt=datetime.fromisoformat(str(value).replace("Z","+00:00"))
        if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc)-dt <= timedelta(hours=FRESHNESS_HOURS)
    except Exception:
        return False

def export():
    DATA_DIR.mkdir(parents=True,exist_ok=True)
    storage=Storage()
    datasets={}
    for rt,name in [("STARTUP","startups"),("PRODUCT","products"),("RESEARCH_PAPER","research_papers"),("MODEL","models"),("DATASET","datasets"),("REPOSITORY","repositories"),("VIDEO","videos"),("NEWS","news"),("JOB","jobs")]:
        db_rows=[canonical_record(r) for r in storage.get_records(rt)]
        db_rows=[r for r in db_rows if r]
        existing_rows=[]
        existing_path=DATA_DIR/f"{name}.json"
        if existing_path.exists():
            try: existing_rows=json.loads(existing_path.read_text(encoding="utf-8"))
            except Exception: existing_rows=[]
        # Merge DB records with previously exported source datasets. This matters when a new
        # adapter is introduced after the project already contains JSON collected by an older run.
        if rt in ("NEWS","JOB"):
            rows=db_rows
        else:
            by_id={str(r.get("id")):r for r in existing_rows if isinstance(r,dict) and r.get("id")}
            for r in db_rows:
                by_id[str(r.get("id"))]=r
            rows=list(by_id.values())
        if rt in ("NEWS","JOB"):
            rows=[r for r in rows if is_fresh(r)]
        datasets[name]=rows
        (DATA_DIR/f"{name}.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf-8")
    for name in AUXILIARY:
        p=DATA_DIR/f"{name}.json"
        if not p.exists(): p.write_text("[]",encoding="utf-8")
        try: datasets[name]=json.loads(p.read_text(encoding="utf-8"))
        except Exception: datasets[name]=[]
    # Curated, source-backed additions survive every incremental export.
    curated=DATA_DIR/"curated"
    if curated.exists():
        for p in curated.glob("*.json"):
            name=p.stem
            try: extra=json.loads(p.read_text(encoding="utf-8"))
            except Exception: extra=[]
            if name=="companies":
                existing={str(x.get("id")) for x in datasets["startups"]}
                datasets["startups"] += [x for x in extra if str(x.get("id")) not in existing]
            elif name in datasets:
                existing={str(x.get("id")) for x in datasets[name]}
                datasets[name] += [x for x in extra if str(x.get("id")) not in existing]
    # Persist merged datasets after curated additions.
    for name,rows in datasets.items():
        if name not in ("relationships","entity_mapping_log"):
            (DATA_DIR/f"{name}.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf-8")
    catalog=[]
    for name,rows in datasets.items():
        if name in ("relationships","entity_mapping_log"): continue
        for row in rows:
            if isinstance(row,dict) and row.get("id"): catalog.append(row)
    (DATA_DIR/"catalog.json").write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding="utf-8")
    mappings=storage.get_all_entity_mappings()
    (DATA_DIR/"entity_mapping_log.json").write_text(json.dumps(mappings,ensure_ascii=False,indent=2),encoding="utf-8")
    storage.close()
    return {k:len(v) for k,v in datasets.items()}, len(catalog), len(mappings)

if __name__=="__main__":
    counts,total,maps=export()
    print(json.dumps({"datasets":counts,"catalog":total,"entity_mappings":maps},indent=2))
