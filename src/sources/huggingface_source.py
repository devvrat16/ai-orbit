from config import HF_TOKEN
from datetime import datetime, timezone

class HuggingFaceSource:
    """Official Hugging Face API adapter for models and datasets."""
    def __init__(self,http): self.http=http

    async def models(self, limit=250):
        headers={"Authorization": f"Bearer {HF_TOKEN}"} if HF_TOKEN else None
        data=await self.http.get_json(f"https://huggingface.co/api/models?sort=lastModified&direction=-1&limit={limit}", extra_headers=headers) or []
        out=[]
        for d in data:
            mid=d.get("id")
            if not mid: continue
            url=f"https://huggingface.co/{mid}"
            task=d.get("pipeline_tag")
            out.append({"schemaVersion":"1.0","recordType":"MODEL","source":{"name":"Hugging Face","url":url},"content":{
                "modelName":mid,"description":task or "Hugging Face model","website":url,"category":task or "AI/ML",
                "provider":mid.split("/")[0] if "/" in mid else None,"license":d.get("license"),
                "modalities":d.get("tags") or [],"downloads":d.get("downloads"),"likes":d.get("likes"),
                "last_modified":d.get("lastModified")
            },"collectedAt":datetime.now(timezone.utc).isoformat()})
        return out

    async def datasets(self, limit=100):
        headers={"Authorization": f"Bearer {HF_TOKEN}"} if HF_TOKEN else None
        data=await self.http.get_json(f"https://huggingface.co/api/datasets?sort=lastModified&direction=-1&limit={limit}", extra_headers=headers) or []
        out=[]
        for d in data:
            did=d.get("id")
            if not did: continue
            url=f"https://huggingface.co/datasets/{did}"
            out.append({"schemaVersion":"1.0","recordType":"DATASET","source":{"name":"Hugging Face","url":url},"content":{
                "datasetName":did,"description":"Hugging Face dataset","website":url,
                "category":"AI Dataset","provider":did.split("/")[0] if "/" in did else None,
                "tags":d.get("tags") or [],"downloads":d.get("downloads"),"likes":d.get("likes"),
                "last_modified":d.get("lastModified")
            },"collectedAt":datetime.now(timezone.utc).isoformat()})
        return out
