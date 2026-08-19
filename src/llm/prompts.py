"""Extraction prompts for each entity type."""

STARTUP_EXTRACTION_PROMPT = """You are a data extraction assistant. Extract structured startup information from the following text.

IMPORTANT: Only extract information that is explicitly present in the text. Do NOT make up or infer data that isn't there. If a field is not available, set it to null.

Return a JSON object with these exact fields:
{
  "entityName": "string - the canonical company/startup name",
  "employeeCount": "integer or null - number of employees",
  "description": "string or null - brief description of what they do",
  "website": "string or null - company website URL",
  "location": "string or null - headquarters location",
  "industry": "string or null - primary industry/sector",
  "founded_year": "integer or null - year the company was founded"
}

Text to extract from:
{content}

Return ONLY the JSON object, no explanation."""

PRODUCT_EXTRACTION_PROMPT = """You are a data extraction assistant. Extract structured product information from the following text.

IMPORTANT: Only extract information that is explicitly present in the text. Do NOT make up or infer data that isn't there. If a field is not available, set it to null.

Return a JSON object with these exact fields:
{
  "startupName": "string - the company/organization that made this product",
  "productName": "string - the name of the product",
  "pricingModel": "string - one of: FREE, FREEMIUM, PAID, ENTERPRISE (or null if unknown)",
  "description": "string or null - what the product does",
  "website": "string or null - product URL",
  "category": "string or null - product category"
}

Text to extract from:
{content}

Return ONLY the JSON object, no explanation."""

PAPER_EXTRACTION_PROMPT = """You are a data extraction assistant. Extract structured research paper information from the following text.

IMPORTANT: Only extract information that is explicitly present in the text. Do NOT make up or infer data that isn't there. If a field is not available, set it to null.

Return a JSON object with these exact fields:
{
  "title": "string - the paper title",
  "authors": ["array of author names"],
  "paper_url": "string - URL to the paper (arxiv, pdf, etc.)",
  "github_url": "string or null - URL to associated GitHub repo",
  "github_stars": "integer or null - star count on GitHub",
  "published_date": "string or null - publication date in ISO-8601 format",
  "abstract": "string or null - paper abstract"
}

Text to extract from:
{content}

Return ONLY the JSON object, no explanation."""

NEWS_EXTRACTION_PROMPT = """You are a data extraction assistant. Extract structured news article information from the following text.

IMPORTANT: Only extract information that is explicitly present in the text. Do NOT make up or infer data that isn't there. If a field is not available, set it to null.

Return a JSON object with these exact fields:
{
  "title": "string - article headline",
  "author": "string or null - author name",
  "date": "string or null - publication date in ISO-8601 format",
  "full_text": "string - the full article text (summarize if too long)",
  "summary": "string - a 2-3 sentence summary of the article",
  "category": "string or null - article category/topic"
}

Text to extract from:
{content}

Return ONLY the JSON object, no explanation."""

JOB_EXTRACTION_PROMPT = """You are a data extraction assistant. Extract structured job posting information from the following text.

IMPORTANT: Only extract information that is explicitly present in the text. Do NOT make up or infer data that isn't there. If a field is not available, set it to null.

Return a JSON object with these exact fields:
{
  "company": "string - company name",
  "title": "string or null - job title",
  "date": "string or null - posting date in ISO-8601 format",
  "is_remote": "boolean - is this a remote position?",
  "role_family": "string or null - one of: Engineering, Machine Learning, Data Science, Research, Product, Design, Management, Infrastructure, Security, Other",
  "location": "string or null - job location",
  "url": "string or null - link to the job posting"
}

Text to extract from:
{content}

Return ONLY the JSON object, no explanation"""


PROMPTS = {
    "STARTUP": STARTUP_EXTRACTION_PROMPT,
    "PRODUCT": PRODUCT_EXTRACTION_PROMPT,
    "RESEARCH_PAPER": PAPER_EXTRACTION_PROMPT,
    "NEWS": NEWS_EXTRACTION_PROMPT,
    "JOB": JOB_EXTRACTION_PROMPT,
}
