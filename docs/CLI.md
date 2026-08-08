# CLI Reference

```bash
skillsbank [--db PATH] [--json] [--compact] COMMAND [ARGS]
```

**Global Options:**
| Option | Default | Description |
|--------|---------|-------------|
| `--db PATH` | `skillsbank.db` | SQLite database path |
| `--json` | off | Output as JSON |
| `--compact` | off | Compact JSON (no indentation) |

## Commands

### search

Full-text search across skills.

```bash
skillsbank search "security audit"
skillsbank search "react" --domain frontend --limit 5
skillsbank search "deploy" --category devops --min-quality 0.7 --json
```

**Options:**
| Option | Description |
|--------|-------------|
| `--domain TEXT` | Filter by domain |
| `--category TEXT` | Filter by capability category |
| `--repo TEXT` | Filter by repo (owner/name format) |
| `--min-quality FLOAT` | Minimum quality score |
| `--max-risk TEXT` | Maximum risk level |
| `--limit INT` | Results per page (default: 20) |
| `--offset INT` | Pagination offset |
| `--facets` | Include facet counts in output |

### autocomplete

Prefix search on skill names.

```bash
skillsbank autocomplete code
skillsbank autocomplete sec --json
```

**Options:**
| Option | Description |
|--------|-------------|
| `--limit INT` | Max results (default: 10) |

### recommend

Get skill recommendations for a task.

```bash
skillsbank recommend "set up a React app with authentication"
skillsbank recommend "write unit tests" --limit 5
skillsbank recommend "deploy to AWS" --installed "skill-id-1,skill-id-2"
```

**Options:**
| Option | Description |
|--------|-------------|
| `--installed TEXT` | Comma-separated skill IDs to exclude |
| `--limit INT` | Max recommendations (default: 10) |

### recommend-for

Get skills similar to or complementary with a specific skill.

```bash
skillsbank recommend-for abc123-def456
```

**Options:**
| Option | Description |
|--------|-------------|
| `--limit INT` | Max recommendations (default: 10) |

### skills list

Browse skills with optional filtering.

```bash
skillsbank skills list
skillsbank skills list --domain security --limit 10
skillsbank skills list --repo nvidia/skills --json
```

**Options:**
| Option | Description |
|--------|-------------|
| `--domain TEXT` | Filter by domain |
| `--repo TEXT` | Filter by repo |
| `--lifecycle TEXT` | Filter by lifecycle status |
| `--limit INT` | Results per page (default: 20) |
| `--offset INT` | Pagination offset |

### skills get

Get detailed information about a specific skill.

```bash
skillsbank skills get abc123-def456
skillsbank skills get abc123-def456 --json
```

### repos

List all indexed repositories.

```bash
skillsbank repos
skillsbank repos --json
```

### compose

Combine multiple skills into a composite workflow.

```bash
skillsbank compose id1 id2 id3 --name "full-stack-deploy"
skillsbank compose id1 id2 --strategy parallel --json
```

**Options:**
| Option | Description |
|--------|-------------|
| `--name TEXT` | Name for the composite skill |
| `--strategy TEXT` | Composition strategy: sequential, parallel, pipeline, conditional |
| `--conflict-resolution TEXT` | How to handle conflicts: fail, warn, prefer_first, prefer_last, merge |

### dedup

Run duplicate detection across all skills.

```bash
skillsbank dedup
skillsbank dedup --min-score 0.8 --json
```

**Options:**
| Option | Description |
|--------|-------------|
| `--min-score FLOAT` | Minimum similarity score (default: 0.40) |

### import

Import or sync skills from a v3 JSON file.

```bash
skillsbank import registry.v3.json
skillsbank import registry.v3.json --dry-run
```

**Options:**
| Option | Description |
|--------|-------------|
| `--dry-run` | Show what would change without applying |

### stats

Show registry statistics.

```bash
skillsbank stats
skillsbank stats --json
```

### rebuild-fts

Rebuild the full-text search index.

```bash
skillsbank rebuild-fts
```

### normalize

Normalize capability taxonomy in the database.

```bash
skillsbank normalize
```

### deps

Show dependency information.

```bash
skillsbank deps                          # Global dependency summary
skillsbank deps --skill-id abc123        # Per-skill dependencies
```

### doctor

Run health checks on the registry database.

```bash
skillsbank doctor
skillsbank doctor --json
```

Checks:
- Database accessible
- Foreign key integrity
- FTS index present
- Capability taxonomy coverage
- Quality scoring coverage
- Security assessment coverage
- Repository health
- Data freshness
- Duplicate rate

### analytics

Run comprehensive analytics.

```bash
skillsbank analytics                     # Full report
skillsbank analytics --section health    # Specific section
skillsbank analytics --section quality --json
```

**Sections:**
| Section | Description |
|---------|-------------|
| `all` | Full report (default) |
| `health` | Health checks |
| `coverage` | Data coverage report |
| `gaps` | Gap analysis (missing data) |
| `quality` | Quality score distribution |
| `ecosystems` | Per-repository health |
| `domains` | Domain distribution |
| `categories` | Category distribution |
| `risks` | Risk level distribution |
| `compatibility` | Agent compatibility stats |
| `dependencies` | Dependency analysis |
| `duplicates` | Duplicate detection summary |

### export

Export skills in various formats.

```bash
skillsbank export json output.json
skillsbank export markdown catalog.md --domain devops
skillsbank export csv skills.csv --min-quality 0.7
```

**Formats:**
- `json` — v3-compatible JSON with full metadata
- `markdown` — Grouped by domain with summaries
- `csv` — Tabular with configurable columns

**Options:**
| Option | Description |
|--------|-------------|
| `--domain TEXT` | Filter by domain |
| `--repo TEXT` | Filter by repo |
| `--min-quality FLOAT` | Minimum quality score |
| `--max-risk TEXT` | Maximum risk level |
| `--limit INT` | Max skills to export |

## Examples

### Find high-quality security skills

```bash
skillsbank search "security" --domain security --min-quality 0.8 --limit 10
```

### Get recommendations for a project

```bash
skillsbank recommend "build a REST API with authentication and deploy to AWS"
```

### Export a curated catalog

```bash
skillsbank export markdown ai-catalog.md --domain ai_ml --min-quality 0.6
```

### Full registry health check

```bash
skillsbank doctor --json | jq '.checks[] | select(.status != "ok")'
```

### Analyze ecosystem coverage

```bash
skillsbank analytics --section ecosystems --json
```

### Find and review duplicates

```bash
skillsbank dedup --min-score 0.8 --json | jq '.similarities[:5]'
```
