import re
from bs4 import BeautifulSoup

class OfficialSiteEnricher:
    """Official-site enrichment for newly discovered records only."""
    def __init__(self,http): self.http=http

    async def run(self, records):
        return await self.enrich(records)

    async def enrich(self, records):
        out=[]
        for r in records:
            content=dict(r.get("content") or {})
            url=content.get("website") or r.get("source",{}).get("url")
            if not url:
                out.append(r); continue
            try:
                html=await self.http.get(url)
                if not html:
                    out.append(r); continue
                soup=BeautifulSoup(html,"lxml")
                title=self._meta(soup,"og:title") or (soup.title.get_text(" ",strip=True) if soup.title else "")
                desc=self._meta(soup,"og:description") or self._meta(soup,"description")
                image=self._meta(soup,"og:image")
                if desc and not content.get("description"): content["description"]=self._clean(desc)
                if title: content["official_page_title"]=self._clean(title)
                if image: content["image_url"]=image
                content["official_site_verified"]=True
                content["official_site_url"]=url
                r=dict(r); r["content"]=content
            except Exception:
                pass
            out.append(r)
        return out

    @staticmethod
    def _meta(soup,name):
        tag=soup.find("meta",attrs={"property":name}) or soup.find("meta",attrs={"name":name})
        return tag.get("content","").strip() if tag else ""
    @staticmethod
    def _clean(text): return re.sub(r"\s+"," ",BeautifulSoup(text,"html.parser").get_text(" ")).strip()[:2500]
