#!/usr/bin/env python3
"""Validate the public trial dataset against the AI Orbit assessment contract."""
import json
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parent; DATA=ROOT/"data"
FILES=["companies","tools","tasks","news","videos","robots","devices","models","repositories","mcp","collections","personal","creative","research_papers","datasets"]
REQ={"id","entity_type","name","description","url","categories","source"}
ents=[]; errors=[]
for f in FILES:
 p=DATA/f"{f}.json"
 if not p.exists(): errors.append(f"missing {f}.json"); continue
 for x in json.loads(p.read_text()):
  ents.append(x); missing=REQ-set(x)
  if missing: errors.append(f"{f}:{x.get('name','?')}: missing {sorted(missing)}")
  if not x.get('url') or not x.get('source',{}).get('url'): errors.append(f"{f}:{x.get('name','?')}: missing source URL")
ids={x.get('id') for x in ents}; rels=json.loads((DATA/"relationships.json").read_text())
rels=[r for r in rels if r.get('source_id') in ids and r.get('target_id') in ids]
types=Counter(r.get('relation') for r in rels)
checks={"entity_count_250_300":250<=len(ents)<=300,"no_schema_errors":not errors,"DEVELOPS":types.get('DEVELOPS',0)>0,"SOLVES":types.get('SOLVES',0)>0,"INTEGRATES_WITH":types.get('INTEGRATES_WITH',0)>0,"RUNS":types.get('RUNS',0)>0,"stable_ids_unique":len(ids)==len(ents)}
print(json.dumps({"entities":len(ents),"relationships":len(rels),"relationship_types":dict(types),"checks":checks,"errors":errors[:20],"valid":all(checks.values())},indent=2))
raise SystemExit(0 if all(checks.values()) else 1)
