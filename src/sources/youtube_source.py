from datetime import datetime, timezone
from config import YOUTUBE_API_KEY

class YouTubeSource:
    """Official YouTube Data API v3 adapter; no page scraping."""
    QUERIES=("AI tools","AI tutorials","AI agents","MCP servers","AI models")
    def __init__(self,http): self.http=http

    async def run(self, per_query=15):
        if not YOUTUBE_API_KEY: return []
        out=[]; seen=set()
        for q in self.QUERIES:
            params=f"part=snippet&q={q.replace(' ','%20')}&type=video&order=date&maxResults={min(per_query,50)}&key={YOUTUBE_API_KEY}"
            data=await self.http.get_json("https://www.googleapis.com/youtube/v3/search?"+params) or {}
            for item in data.get("items",[]):
                vid=(item.get("id") or {}).get("videoId")
                sn=item.get("snippet") or {}
                if not vid or vid in seen: continue
                seen.add(vid); url=f"https://www.youtube.com/watch?v={vid}"
                out.append({"schemaVersion":"1.0","recordType":"VIDEO","source":{"name":"YouTube","url":url},"content":{
                    "title":sn.get("title") or "","description":sn.get("description") or "","website":url,
                    "category":"AI Video","channel":sn.get("channelTitle"),"published_at":sn.get("publishedAt"),
                    "thumbnail":((sn.get("thumbnails") or {}).get("high") or {}).get("url"),"query":q
                },"collectedAt":datetime.now(timezone.utc).isoformat()})
        return out
