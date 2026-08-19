#!/usr/bin/env python3
"""AI Signal / AI Orbit unified ingestion orchestrator.

Normal mode is incremental: source discovery may revisit current listings, but only
records with unseen source URLs are persisted and downstream enrichment is run only
for the newly inserted records. Existing records remain unchanged.

Use --refresh-metrics for explicit dynamic metric refreshes such as GitHub stars.
"""
from __future__ import annotations
import argparse, asyncio, json, logging, sys
from datetime import datetime, timezone
from pathlib import Path
from src.scrapers.paper_scraper import PaperScraper

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))

from config import TARGET_STARTUPS,TARGET_PRODUCTS,TARGET_PAPERS,OUTPUT_DIR,FRESHNESS_HOURS,OFFICIAL_ENRICH_LIMIT,YOUTUBE_PER_QUERY,HF_MODEL_LIMIT,HF_DATASET_LIMIT,GITHUB_PER_QUERY
from src.storage import Storage
from src.http_client import HttpClient
from src.entity.resolver import EntityResolver
from src.scrapers.yc_scraper import YCScraper
from src.scrapers.ai_tool_scraper import AIToolScraper
from src.scrapers.paper_scraper import PaperScraper
from src.scrapers.news_scraper import NewsScraper
from src.scrapers.job_scraper import JobScraper
from src.sources.github_source import GitHubSource
from src.sources.huggingface_source import HuggingFaceSource
from src.sources.youtube_source import YouTubeSource
from src.sources.official_site import OfficialSiteEnricher

log=logging.getLogger("ai_signal")

def setup_logging(verbose=False):
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[logging.StreamHandler(sys.stdout),logging.FileHandler(ROOT/"pipeline.log",mode="a")]
    )

def persist_new(storage, records):
    added=0
    for r in records:
        if storage.insert_if_new(
            r.get("recordType",""),r.get("source",{}).get("name",""),
            r.get("source",{}).get("url",""),r.get("content",{}),
            r.get("collectedAt","")
        ):
            added+=1
    return added

async def safe_scrape(label, scraper, target=None):
    try:
        if target is None: return await scraper.run()
        return await scraper.run(target)
    except Exception as exc:
        log.exception("%s skipped: %s",label,exc)
        return []

def resolve_entities(storage):
    resolver=EntityResolver(storage)
    stats={}
    for record_type,field in [("STARTUP","entityName"),("PRODUCT","startupName"),("JOB","company")]:
        changed=0
        for row in storage.get_records(record_type):
            content=row["content"]
            raw=content.get(field,"")
            if not raw: continue
            canonical=resolver.resolve(raw,row.get("source_name",""),record_type)
            if canonical!=raw:
                content[field]=canonical
                storage.upsert_record(record_type,row["source_name"],row["source_url"],content,row["collected_at"],update_existing=True)
                changed+=1
        stats[record_type]={"changed":changed}
    stats["resolver"]=resolver.get_stats()
    return stats

def export_all():
    import subprocess
    subprocess.run([sys.executable,str(ROOT/"export_catalog.py")],check=True)
    subprocess.run([sys.executable,str(ROOT/"build_relationships.py")],check=True)

async def run(phases,verbose=False):
    setup_logging(verbose)
    storage=Storage(); http=HttpClient(); added={}; sources={}
    try:
        # Phase I: bulk/API-first discovery. Every source is isolated and incremental.
        if "I" in phases:
            startup_candidates=await safe_scrape("startups / AI directories",YCScraper(http,storage),TARGET_STARTUPS)
            product_candidates=await safe_scrape("AI directories",AIToolScraper(http,storage),TARGET_PRODUCTS)

            # Official product/company sites are used only to enrich NEW candidates before persistence.
            new_startups=[r for r in startup_candidates if not storage.is_url_collected(r.get("source",{}).get("url",""))]
            new_products=[r for r in product_candidates if not storage.is_url_collected(r.get("source",{}).get("url",""))]
            new_startups=await safe_scrape("official company sites",OfficialSiteEnricher(http),new_startups[:OFFICIAL_ENRICH_LIMIT])
            new_products=await safe_scrape("official product sites",OfficialSiteEnricher(http),new_products[:OFFICIAL_ENRICH_LIMIT])
            added["startups"]=persist_new(storage,new_startups)
            added["products"]=persist_new(storage,new_products)
            sources["official_product_sites"]={"new_candidates_enriched":len(new_startups)+len(new_products)}
            sources["ai_directories"]={"candidates":len(product_candidates)}

            papers=await safe_scrape("research papers",PaperScraper(http,storage),TARGET_PAPERS)
            added["research_papers"]=persist_new(storage,papers)

            gh=await safe_scrape("GitHub API",GitHubSource(http),GITHUB_PER_QUERY)
            added["repositories"]=persist_new(storage,gh)
            sources["github"]={"candidates":len(gh),"token_configured":bool(__import__('config').GITHUB_TOKEN)}

            hf=HuggingFaceSource(http)
            hf_models=await safe_scrape("Hugging Face models",hf.models,HF_MODEL_LIMIT)
            hf_datasets=await safe_scrape("Hugging Face datasets",hf.datasets,HF_DATASET_LIMIT)
            added["models"]=persist_new(storage,hf_models)
            added["datasets"]=persist_new(storage,hf_datasets)
            sources["hugging_face"]={"models":len(hf_models),"datasets":len(hf_datasets)}

            videos=await safe_scrape("YouTube API",YouTubeSource(http),YOUTUBE_PER_QUERY)
            added["videos"]=persist_new(storage,videos)
            sources["youtube"]={"candidates":len(videos),"api_key_configured":bool(__import__('config').YOUTUBE_API_KEY)}

        if "II" in phases:
            news=await safe_scrape("news",NewsScraper(http,storage))
            jobs=await safe_scrape("jobs",JobScraper(http,storage))
            added["news"]=persist_new(storage,news)
            added["jobs"]=persist_new(storage,jobs)
            sources["news_rss"]={"fresh_candidates":len(news),"freshness_hours":FRESHNESS_HOURS}

        if "IV" in phases:
            resolution=resolve_entities(storage)
        else:
            resolution={}
        if "VI" in phases or "IV" in phases:
            export_all()
        counts=storage.counts()
        result={"mode":"incremental","sources":sources,"added":added,"resolution":resolution,"sqlite_counts":counts,"freshness_hours":FRESHNESS_HOURS,"timestamp":datetime.now(timezone.utc).isoformat()}
        OUTPUT_DIR.mkdir(parents=True,exist_ok=True)
        (OUTPUT_DIR/"pipeline_summary.json").write_text(json.dumps(result,indent=2,default=str),encoding="utf-8")
        print(json.dumps(result,indent=2,default=str))
        return result
    finally:
        await http.close(); storage.close()

def main():
    ap=argparse.ArgumentParser(description="AI Signal unified AI ecosystem ingestion pipeline")
    ap.add_argument("--phases",default="I,II,IV,VI",help="Comma-separated: I bulk, II fresh signals, IV resolution, VI export")
    ap.add_argument("--startups-only",action="store_true")
    ap.add_argument("--products-only",action="store_true")
    ap.add_argument("--papers-only",action="store_true")
    ap.add_argument("--news-only",action="store_true")
    ap.add_argument("--jobs-only",action="store_true")
    ap.add_argument("--relationships-only",action="store_true")
    ap.add_argument("--export-only",action="store_true")
    ap.add_argument("-v","--verbose",action="store_true")
    args=ap.parse_args()
    if args.relationships_only:
        setup_logging(args.verbose); export_all(); return
    if args.export_only:
        setup_logging(args.verbose); export_all(); return
    if args.startups_only: phases=["I"]; target="startups"
    elif args.products_only: phases=["I"]; target="products"
    elif args.papers_only: phases=["I"]; target="research_papers"
    elif args.news_only: phases=["II"]; target="news"
    elif args.jobs_only: phases=["II"]; target="jobs"
    else: target=None; phases=[x.strip() for x in args.phases.split(",") if x.strip()]
    # For focused modes, use the same pipeline but suppress unrelated collectors.
    if target:
        async def focused():
            setup_logging(args.verbose); storage=Storage(); http=HttpClient()
            try:
                if target=="startups": n=persist_new(storage,await safe_scrape(target,YCScraper(http,storage),TARGET_STARTUPS))
                elif target=="products": n=persist_new(storage,await safe_scrape(target,AIToolScraper(http,storage),TARGET_PRODUCTS))
                elif target=="research_papers": n=persist_new(storage,await safe_scrape(target,PaperScraper(http,storage),TARGET_PAPERS))
                elif target=="news": n=persist_new(storage,await safe_scrape(target,NewsScraper(http,storage)))
                else: n=persist_new(storage,await safe_scrape(target,JobScraper(http,storage)))
                resolve_entities(storage); export_all(); print(json.dumps({"mode":"incremental","added":{target:n},"counts":storage.counts()},indent=2))
            finally:
                await http.close(); storage.close()
        asyncio.run(focused()); return
    asyncio.run(run(phases,args.verbose))

if __name__=="__main__": main()
