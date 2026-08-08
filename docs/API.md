# REST API Reference

Base URL: `http://localhost:8000`

Start server:
```bash
uvicorn skillsbank.api:app --reload --port 8000
```

## Endpoints

### Health

```
GET /health
```

Returns server health and database statistics.

**Response:**
```json
{
  "status": "healthy",
  "skills": 1065,
  "versions": 1065,
  "repos": 36
}
```

### Search

```
GET /search?q={query}&domain={domain}&category={category}&repo={repo}&min_quality={float}&limit={int}&offset={int}&facets={bool}
```

Full-text search with BM25 ranking and faceted filtering.

**Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| q | string | required | Search query (supports AND/OR/NOT, quoted phrases) |
| domain | string | | Filter by domain (security, frontend, backend, etc.) |
| category | string | | Filter by capability category |
| repo | string | | Filter by source repository (owner/name) |
| min_quality | float | | Minimum quality score (0.0-1.0) |
| max_risk | string | | Maximum risk level (LOW, MEDIUM, HIGH, CRITICAL) |
| lifecycle | string | | Lifecycle status (active, deprecated, archived) |
| has_mcp | bool | | Filter MCP-compatible skills |
| format | string | | Filter by format (SKILL.md, AGENTS.md, README) |
| limit | int | 20 | Results per page |
| offset | int | 0 | Pagination offset |
| facets | bool | false | Include facet counts |

**Response:**
```json
{
  "results": [
    {
      "skill_id": "abc123",
      "name": "security-audit",
      "summary": "Full security audit...",
      "domain": "security",
      "repo": "owner/repo",
      "score": 8.5,
      "quality": 0.82,
      "risk_level": "LOW"
    }
  ],
  "total": 42,
  "limit": 20,
  "offset": 0,
  "facets": {
    "domain": {"security": 15, "devops": 10},
    "category": {"security": 20, "cloud": 8}
  }
}
```

### Autocomplete

```
GET /autocomplete?q={prefix}&limit={int}
```

Prefix search on skill names.

**Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| q | string | required | Name prefix |
| limit | int | 10 | Max results |

**Response:**
```json
{
  "suggestions": [
    {"skill_id": "abc123", "name": "code-review", "domain": "code_quality"}
  ]
}
```

### Get Skill

```
GET /skills/{skill_id}
```

Get detailed skill information including capabilities and tags.

**Response:**
```json
{
  "skill_id": "abc123",
  "name": "security-audit",
  "display_name": "Security Audit",
  "summary": "Full security audit...",
  "domain": "security",
  "repo": "owner/repo",
  "capabilities": [
    {"name": "vulnerability scanning", "canonical": "vulnerability_scanning", "category": "security"}
  ],
  "tags": [
    {"name": "owasp", "source": "parser"}
  ],
  "quality": {"overall": 0.82, "documentation": 0.9, "metadata": 0.8},
  "security": {"risk_level": "LOW", "risk_factors": []},
  "compatibility": {"claude": "SUPPORTED", "codex": "SUPPORTED"}
}
```

### List Skills

```
GET /skills?domain={domain}&repo={repo}&limit={int}&offset={int}
```

Browse skills with optional filtering.

**Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| domain | string | | Filter by domain |
| repo | string | | Filter by repo (owner/name) |
| lifecycle | string | | Filter by lifecycle status |
| limit | int | 20 | Results per page |
| offset | int | 0 | Pagination offset |

### Recommend

```
GET /recommend?task={description}&limit={int}
```

Get skill recommendations for a task.

**Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| task | string | required | Natural language task description |
| installed | string | | Comma-list of installed skill IDs to exclude |
| limit | int | 10 | Max recommendations |

**Response:**
```json
{
  "task": "set up CI/CD pipeline",
  "recommendations": [
    {
      "skill_id": "abc123",
      "name": "ci-cd-and-automation",
      "reason": "task_match",
      "score": 0.85,
      "summary": "Automates CI/CD pipeline setup..."
    }
  ],
  "total": 5
}
```

### Recommend for Skill

```
GET /recommend/{skill_id}?limit={int}
```

Get skills similar to or complementary with a specific skill.

### Repositories

```
GET /repos
```

List all indexed repositories.

**Response:**
```json
{
  "repos": [
    {
      "id": "repo-abc123",
      "url": "https://github.com/owner/repo",
      "owner": "owner",
      "name": "repo",
      "skill_count": 15,
      "ecosystem": "github"
    }
  ]
}
```

### Export

```
GET /export/json?domain={domain}&repo={repo}&min_quality={float}&limit={int}
GET /export/csv?domain={domain}&repo={repo}&limit={int}
GET /export/markdown?domain={domain}&limit={int}
GET /export/stats
```

Export skills in various formats with optional filtering.

**Export Stats Response:**
```json
{
  "total_skills": 1065,
  "by_domain": {"security": 150, "frontend": 120},
  "by_repo": {"nvidia/skills": 331, "microsoft/skills": 194}
}
```

### Search Stats

```
GET /search/stats
```

Returns FTS index statistics.

### Admin

```
POST /admin/rebuild-fts
```

Rebuild the full-text search index. Returns counts of indexed entries.

## Error Responses

All errors return structured JSON:

```json
{
  "error": "validation_error",
  "message": "Invalid query parameter",
  "code": 422
}
```

| Code | Meaning |
|------|---------|
| 400 | Bad request |
| 404 | Not found |
| 422 | Validation error |
| 429 | Rate limited |
| 500 | Internal error (message sanitized) |

## Rate Limiting

API endpoints are rate-limited. Exceeding limits returns 429 with `Retry-After` header.

## Authentication

Currently no authentication required. API is designed for local/single-user use.
