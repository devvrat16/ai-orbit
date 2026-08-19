from datetime import datetime, timezone
import re
from .schemas import Relationship


def _norm(value):
    value = str(value or "").strip().lower()
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _compact(value):
    return re.sub(r"[^a-z0-9]", "", _norm(value))


# Conservative aliases. These are deterministic canonicalization aids, not generated facts.
ALIASES = {
    "open ai": "openai", "openai inc": "openai", "openai inc.": "openai",
    "anthropic ai": "anthropic", "anthropic pbc": "anthropic",
    "mistral": "mistral ai", "mistralai": "mistral ai", "mistral ai": "mistral ai",
    "cohere ai": "cohere", "cohereforai": "cohere", "cohere for ai": "cohere",
    "perplexity ai": "perplexity", "perplexity-ai": "perplexity",
    "hugging face": "hugging face", "huggingface": "hugging face",
}


def canonical_org(value):
    n = _norm(value)
    return ALIASES.get(n, n)


def _provider_matches(company_name, provider):
    if not company_name or not provider:
        return False
    c = canonical_org(company_name)
    p = canonical_org(provider)
    if c == p:
        return True
    cc, pp = _compact(c), _compact(p)
    if cc and pp and (cc in pp or pp in cc):
        return True
    # Explicit known provider namespace patterns.
    provider_namespaces = {
        "openai": {"openai"},
        "anthropic": {"anthropic"},
        "mistral ai": {"mistralai", "mistral"},
        "cohere": {"cohere", "cohereforai"},
        "perplexity": {"perplexity"},
        "hugging face": {"huggingface", "huggingfacetb", "huggingfaceh4"},
    }
    return p in {canonical_org(x) for x in provider_namespaces.get(c, set())}


def _repo_owner(name):
    text = str(name or "")
    return text.split("/", 1)[0] if "/" in text else ""


def _url_key(url):
    return str(url or "").rstrip("/").lower()


class RelationshipMapper:
    """Build only source-backed, deterministic relationships from existing entities."""

    def build(self, companies, products, models, mcp=None, devices=None, repos=None, tasks=None, papers=None):
        relationships = []
        seen = set()
        mcp = mcp or []
        devices = devices or []
        repos = repos or []
        tasks = tasks or []
        papers = papers or []

        def add(source, relation, target, evidence, confidence, reason, extra=None):
            if not source or not target or source.id == target.id:
                return
            key = (source.id, relation, target.id)
            if key in seen:
                return
            seen.add(key)
            metadata = {"reason": reason}
            if extra:
                metadata.update(extra)
            relationships.append(
                Relationship(
                    source_id=source.id,
                    source_name=source.name,
                    relation=relation,
                    target_id=target.id,
                    target_name=target.name,
                    evidence_url=evidence or source.url or target.url,
                    confidence=confidence,
                    extracted_at=datetime.now(timezone.utc),
                    metadata=metadata,
                )
            )

        # Company -> Product: explicit ProductEntity.startup_name.
        for product in products:
            startup = getattr(product, "startup_name", None)
            if startup:
                for company in companies:
                    if canonical_org(company.name) == canonical_org(startup):
                        add(company, "DEVELOPS", product, product.url, 0.99, "product.startup_name")
                        break

        # Company -> Model: explicit Hugging Face provider namespace with deterministic aliases.
        for model in models:
            provider = getattr(model, "provider", None)
            if not provider:
                continue
            for company in companies:
                if _provider_matches(company.name, provider):
                    add(company, "DEVELOPS", model, model.url, 0.96, "model.provider")
                    break

        # Company -> Repository: explicit GitHub owner namespace.
        for repo in repos:
            owner = _repo_owner(getattr(repo, "name", ""))
            if not owner:
                continue
            for company in companies:
                if _provider_matches(company.name, owner):
                    add(company, "MAINTAINS", repo, repo.url, 0.95, "github.repository_owner")
                    break

        # MCP -> Tool: only when the tool name is explicitly present in MCP name/description.
        for server in mcp:
            text = _norm(f"{getattr(server, 'name', '')} {getattr(server, 'description', '')}")
            if not text:
                continue
            for product in products:
                pname = _norm(product.name)
                if len(pname) >= 4 and re.search(rf"(?<![a-z0-9]){re.escape(pname)}(?![a-z0-9])", text):
                    add(server, "INTEGRATES_WITH", product, server.url, 0.90, "tool.name explicitly present in MCP metadata")

        # Tool -> Task: deterministic keyword evidence from tool name/description/categories.
        task_keywords = {
            "text generation": ["chat", "writing", "writer", "text", "copywriting", "summar"],
            "image generation": ["image", "photo", "design", "art", "visual", "diffusion"],
            "speech recognition": ["speech", "transcrib", "voice to text", "asr"],
            "text classification": ["classif", "moderation", "sentiment"],
            "object detection": ["object detection", "computer vision", "detect"],
            "question answering": ["question", "answer", "qa", "search engine"],
            "embeddings": ["embedding", "vector", "semantic search", "retrieval"],
            "translation": ["translation", "translate", "localization"],
        }
        for product in products:
            text = _norm(f"{product.name} {product.description} {' '.join(product.categories)}")
            for task in tasks:
                keywords = task_keywords.get(_norm(task.name), [])
                hits = [k for k in keywords if k in text]
                if hits:
                    add(product, "SOLVES", task, product.url, 0.78, "deterministic task keyword evidence", {"matched_keywords": hits})

        # Paper -> Repository: explicit github_url on the paper matching a collected repository.
        repo_by_url = {_url_key(getattr(r, "url", "")): r for r in repos if getattr(r, "url", None)}
        for paper in papers:
            github_url = getattr(paper, "github_url", None)
            if not github_url:
                continue
            repo = repo_by_url.get(_url_key(github_url))
            if repo:
                add(paper, "HAS_REPOSITORY", repo, getattr(paper, "paper_url", None) or paper.url, 0.99, "paper.github_url explicitly matches GitHub repository")

        # Device -> Model: only if a device object explicitly contains a model reference.
        for device in devices:
            model_ref = getattr(device, "model_name", None) or getattr(device, "runs_model", None)
            if not model_ref:
                continue
            ref = _norm(model_ref)
            for model in models:
                if _norm(model.name) == ref or _compact(model.name) == _compact(model_ref):
                    add(device, "RUNS", model, device.url, 0.99, "device.model reference")
                    break

        return relationships
