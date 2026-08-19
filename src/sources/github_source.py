from datetime import datetime, timezone
from urllib.parse import quote_plus
from config import GITHUB_TOKEN

class GitHubSource:
    """Official GitHub REST API adapter for repositories and MCP candidates."""
    QUERIES = ("artificial intelligence", "machine learning", "ai agent", "mcp server")
    def __init__(self, http): self.http=http

    async def run(self, per_query=50):
        out=[]; seen=set()
        headers={"Accept":"application/vnd.github+json"}
        if GITHUB_TOKEN: headers["Authorization"]=f"Bearer {GITHUB_TOKEN}"
        for q in self.QUERIES:
            url=f"https://api.github.com/search/repositories?q={quote_plus(q)}&sort=stars&order=desc&per_page={min(per_query,100)}"
            payload=await self.http.get_json(url, extra_headers=headers) or {}
            for d in payload.get("items",[]):
                html=d.get("html_url")
                if not html or html in seen: continue
                seen.add(html)
                text=f"{d.get('name','')} {d.get('description') or ''}".lower()
                categories=["Repository","Open Source"]
                if "mcp" in text: categories.append("MCP")
                out.append({
                    "schemaVersion":"1.0","recordType":"REPOSITORY",
                    "source":{"name":"GitHub","url":html},
                    "content":{
                        "name":d.get("full_name") or d.get("name") or "",
                        "description":d.get("description") or "",
                        "website":html,"categories":categories,
                        "stars":d.get("stargazers_count"),
                        "primary_language":d.get("language"),
                        "last_updated":d.get("updated_at"),
                        "owner":(d.get("owner") or {}).get("login"),
                        "license":((d.get("license") or {}).get("spdx_id")),
                        "topics":d.get("topics") or []
                    },
                    "collectedAt":datetime.now(timezone.utc).isoformat()
                })
        return out
