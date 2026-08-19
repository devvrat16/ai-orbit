"""Build deterministic, source-backed relationships from the canonical JSON datasets."""
import json
from pathlib import Path
from datetime import datetime, timezone
from src.schemas import CompanyEntity, ProductEntity, ModelEntity, RepositoryEntity, MCPServerEntity, Entity, ResearchPaperEntity, Source
from src.relationships import RelationshipMapper
from config import DATA_DIR

def load(name):
    p=DATA_DIR/f"{name}.json"
    if not p.exists(): return []
    return json.loads(p.read_text(encoding="utf-8"))

def build():
    companies=[CompanyEntity.model_validate(x) for x in load("startups")]
    products=[ProductEntity.model_validate(x) for x in load("products")]
    models=[ModelEntity.model_validate(x) for x in load("models")]
    repo_rows=load("repositories")
    # Materialize GitHub repositories explicitly referenced by papers. This is source-backed,
    # because the URL originates in the paper metadata; no repository is invented from a name.
    seen_urls={str(x.get("url","")).rstrip("/").lower() for x in repo_rows}
    for paper in load("research_papers"):
        gh=str(paper.get("github_url") or "").rstrip("/")
        if gh and "github.com/" in gh and gh.lower() not in seen_urls:
            repo_name=gh.split("github.com/",1)[1]
            repo_rows.append({
                "id": __import__("uuid").uuid5(__import__("uuid").NAMESPACE_URL, "repository::"+gh.lower()).hex,
                "entity_type":"REPOSITORY","name":repo_name,
                "description":"Repository explicitly referenced by the research paper.",
                "url":gh,"categories":["open-source","research-code"],
                "source":{"name":"GitHub (paper reference)","url":gh},
                "stars":None,"primary_language":None,"last_updated":None
            })
            seen_urls.add(gh.lower())
    # Persist the expanded repository catalog for the dashboard.
    (DATA_DIR/"repositories.json").write_text(json.dumps(repo_rows,ensure_ascii=False,indent=2),encoding="utf-8")
    repos=[RepositoryEntity.model_validate(x) for x in repo_rows]
    mcp=[MCPServerEntity.model_validate(x) for x in load("mcp")]
    tasks=[Entity.model_validate(x) for x in load("tasks")]
    papers=[ResearchPaperEntity.model_validate(x) for x in load("research_papers")]
    devices=[Entity.model_validate(x) for x in load("devices")]
    rels=RelationshipMapper().build(companies,products,models,mcp=mcp,devices=devices,repos=repos,tasks=tasks,papers=papers)
    # Additional source-backed robot relationships from official robot pages.
    from src.schemas import Relationship
    from src.relationships import canonical_org
    by_company={canonical_org(c.name):c for c in companies}
    for robot in load("robots"):
        company_name=robot.get("company")
        company=by_company.get(canonical_org(company_name)) if company_name else None
        if company:
            rels.append(Relationship(
                source_id=company.id, source_name=company.name, relation="DEVELOPS",
                target_id=robot["id"], target_name=robot["name"], evidence_url=robot["url"],
                confidence=0.99, metadata={"reason":"robot.company explicitly present in source-backed robot metadata"}
            ))
    old=[]
    p=DATA_DIR/"relationships.json"
    if p.exists():
        try: old=json.loads(p.read_text(encoding="utf-8"))
        except: old=[]
    by={(r.get("source_id"),r.get("relation"),r.get("target_id")):r for r in old}
    for r in rels:
        by[(r.source_id,r.relation,r.target_id)]=r.model_dump(mode="json")
    final=list(by.values())
    p.write_text(json.dumps(final,ensure_ascii=False,indent=2),encoding="utf-8")
    return final

if __name__=="__main__":
    final=build()
    from collections import Counter
    print(json.dumps({"total":len(final),"types":dict(Counter(x["relation"] for x in final))},indent=2))
