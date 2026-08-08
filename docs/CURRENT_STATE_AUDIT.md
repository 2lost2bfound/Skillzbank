# SkillsBank — Current State Audit (Phase 0)

**Date:** 2026-08-07
**Auditor:** automated
**Registry version:** 2.0.0
**Registry file:** `/home/k/skill indexer/registry.json` (997 KB)

---

## 1. Architecture Overview

### Current Architecture

The entire project is a **single JSON file**. There are:

- **Zero scripts** (no parsers, crawlers, generators, builders)
- **Zero tests**
- **Zero documentation**
- **Zero configuration files**
- **Zero migrations**
- **Zero database**
- **Zero CLI**
- **Zero API**
- **Zero dependencies** (no package.json, requirements.txt, pyproject.toml)

The registry was built manually via ad-hoc Python scripts executed inline during chat sessions. Each script was ephemeral — nothing was saved. The build process is **not reproducible**.

### File Inventory

```
/home/k/skill indexer/
├── registry.json          (997,487 bytes — the only file)
└── docs/
    └── CURRENT_STATE_AUDIT.md  (this file)
```

### Build/Import Workflow

1. User provides repo URLs or `owner/repo` slugs
2. Ephemeral Python script clones repos or calls GitHub API
3. Script finds `SKILL.md` files via `glob` or tree traversal
4. Script parses content (regex/heuristic extraction)
5. Script generates UUID5 IDs from `https://github.com/{repo}/{skill_path}`
6. Script appends to in-memory list and writes `registry.json`

**No incremental sync. No versioning. No rollback. No reproducibility.**

---

## 2. Registry Schema (Current v2)

```json
{
  "version": "2.0.0",
  "generated_at": "2026-08-08T03:15:53.977236+00:00",
  "total_skills": 1065,
  "total_repos": 36,
  "sources": { "nvidia/skills": 331, ... },
  "skills": [
    {
      "id": "6ea34e93-d625-5ec2-b9c5-a4a7f414622e",
      "name": "code-review",
      "repo": "mattpocock/skills",
      "skill_path": "skills/engineering/code-review/SKILL.md",
      "summary": "Two-axis code review...",
      "domain": "code-review",
      "capabilities": ["parallel_sub_agent_review", ...],
      "input_shape": { "format": "natural_language", "required": [] },
      "output_shape": { "format": "markdown" },
      "external_dependencies": [],
      "ecosystem_metadata": {},
      "tags": ["review", "quality", ...]
    }
  ]
}
```

### Schema Field Analysis

| Field | Type | Populated | Issues |
|-------|------|-----------|--------|
| `id` | UUID5 string | 1065/1065 | Stable, deterministic, no duplicates |
| `name` | string | 1065/1065 | Free-form, not normalized |
| `repo` | string | 1065/1065 | `owner/repo` format |
| `skill_path` | string | 1065/1065 | Relative path in repo |
| `summary` | string | 1065/1065 | 39 broken, 26 very short |
| `domain` | string | 1065/1065 | 33 unique, 84 "general" |
| `capabilities` | string[] | 1065/1065 | 1050 unique strings, no taxonomy |
| `input_shape` | object/str | 838 obj / 227 str | **228 records are raw strings, not objects** |
| `output_shape` | object/str | 837 obj / 228 str | **228 records are raw strings, not objects** |
| `external_dependencies` | string[] | 13/1065 | **98.8% empty** |
| `ecosystem_metadata` | object | 985/1065 | 80 empty, 1 has license |
| `tags` | string[] | 1065/1065 | Good coverage |

### Missing Fields (Not in Schema at All)

- `commit_sha` — not tracked
- `content_hash` — not tracked
- `imported_at` — not tracked
- `last_checked_at` — not tracked
- `parser_version` — not tracked
- `branch/tag` — not tracked
- `license` — not tracked (1 exception in ecosystem_metadata)
- `version` (skill version) — not tracked
- `long_description` — not tracked
- `use_cases` / `anti_use_cases` — not tracked
- `risk_class` — not tracked
- `compatibility` — not tracked
- `quality_score` — not tracked
- `relationships` — not tracked
- `aliases` — not tracked

---

## 3. Data Quality Measurements

### 3.1 Record Counts

| Metric | Value |
|--------|-------|
| Total skills | 1,065 |
| Unique repos in skills | 36 |
| Repos in `sources` dict | 18 |
| Repos missing from `sources` | 18 |
| Unique IDs | 1,065 (0 duplicates) |
| Unique names | 1,054 |
| Duplicate name groups | 11 |
| Unique repo+path combos | 1,065 (0 duplicates) |

### 3.2 Duplicate Analysis

#### Exact Name Duplicates (11 groups)

| Name | Count | Repos |
|------|-------|-------|
| `skill-creator` | 3 | anthropics, openai, microsoft |
| `code-review` | 2 | mattpocock, coderabbitai |
| `prototype` | 2 | mattpocock, emilkowalski |
| `mcp-builder` | 2 | anthropics, microsoft |
| `pdf` | 2 | anthropics, openai |
| `firebase-basics` | 2 | firebase, google |
| `openai-docs` | 2 | openai, openai (within-repo duplicate) |
| `applicationinsights-web-ts` | 2 | microsoft, microsoft (within-repo) |
| `entra-agent-id` | 2 | microsoft, microsoft (within-repo) |
| `nvidia-skill-finder` | 2 | nvidia, nvidia (within-repo) |
| `opencodex` | 2 | @bitkyc08, lidge-jun |

#### Content-Identical Skills (same summary + capabilities)

- `firebase-basics` × 2 — identical
- `openai-docs` × 2 — identical
- `applicationinsights-web-ts` × 2 — identical
- `nvidia-skill-finder` × 2 — identical
- 8 `zhang*-perspective` / `*-perspective` skills from nuwa-skill — identical template

#### Near-Duplicate Names

All 11 name-duplicate groups are also near-duplicates (normalized). No additional near-duplicates found via normalization.

#### Same-Name, Different-Content Skills

- `code-review`: similarity=0.30 (different approaches)
- `prototype`: similarity=0.10 (different goals)
- `mcp-builder`: similarity=0.12 (different guides)
- `pdf`: similarity=0.28 (different tooling)

These are **functional overlaps**, not true duplicates.

### 3.3 Summary Quality

| Metric | Count |
|--------|-------|
| Total summaries | 1,065 |
| Empty | 0 |
| Very short (<20 chars) | 26 |
| Broken (markdown artifacts) | 39 |

**Broken summary examples:**

- `stripe-best-practices`: `| Building… | Recommended API | Details | | --- |`
- `stripe-docs`: `` ```bash stripe docs /payments ``` ``
- `google-agents-cli-onboarding`: `> [!TIP] **One-Time Setup**...`
- `azure-ai`: `| Service | Use When | MCP Tools | CLI | |--------`
- `deploy`: `| Property | Value | |----------|-------| | Best f`

These are raw markdown table fragments that leaked through the parser.

### 3.4 Input/Output Shape Quality

| Metric | input_shape | output_shape |
|--------|-------------|--------------|
| Valid object format | 838 (78.7%) | 837 (78.6%) |
| Raw string (not object) | 228 (21.4%) | 228 (21.4%) |
| Null/empty | 227 (21.3%) | 227 (21.3%) |

**The 228 string-format records** are from repos where the parser failed to produce structured objects and stored raw strings instead.

**Format distribution (valid objects):**

- input: `natural_language` (836), `cli_command` (1), `unknown` (1)
- output: `markdown` (834), `html` (1), `office_document` (1), `proxy_server` (1)

### 3.5 Dependency Extraction Quality

| Metric | Value |
|--------|-------|
| Empty `external_dependencies` | 1,052/1,065 (98.8%) |
| Non-empty | 13 (1.2%) |

**Critical gap:** The dependency extraction is essentially non-functional. Skills that require Ghidra, IDA Pro, ffmpeg, Docker, Playwright, specific Python packages, etc. all show zero dependencies.

### 3.6 Domain Classification

| Domain | Count | Notes |
|--------|-------|-------|
| ml | 262 | ML/AI training, inference, deployment |
| devops | 188 | Azure, cloud infra, deployment |
| security | 133 | Reverse engineering, pentesting, forensics |
| design | 85 | UI/UX, animation, visual |
| general | 84 | **Suspiciously large catch-all** |
| frontend | 51 | React, Angular, web UI |
| api | 44 | API integration, SDKs |
| documentation | 36 | Docs, guides, templates |
| data | 35 | Data analysis, spreadsheets |
| finance-trading | 21 | Trading, financial analysis |
| animation-video | 18 | Video production, animation |
| creative | 17 | Art, branding, writing |
| embedded | 13 | Hardware, IoT, embedded |
| planning | 10 | Project planning, specs |
| meta | 9 | Skill creation, meta-tooling |
| testing | 8 | QA, test automation |
| git | 6 | Git workflows |
| web-search | 6 | Web research |
| writing | 5 | Content writing |
| document-processing | 5 | PDF, DOCX, XLSX |
| ...13 more | <5 each | |

**Issues:**

- 84 skills in "general" — needs subclassification
- "ml" (262) is overloaded — conflates training, inference, deployment, MLOps
- "devops" (188) conflates CI/CD, cloud infra, monitoring, Azure-specific
- "security" (133) includes CTF, reverse engineering, malware analysis, pentesting — all very different
- 47 security-domain skills have no security-related capabilities

### 3.7 Capability Analysis

| Metric | Value |
|--------|-------|
| Unique capability strings | 1,050 |
| Empty capabilities | 0 |

**Top capabilities:**

- `azure`: 142 (ecosystem-specific, not a capability)
- `ai-security`: 70
- `reverse-engineering`: 69
- `doca`: 60 (NVIDIA-specific, opaque)
- `tao`: 57 (NVIDIA-specific, opaque)
- `financial-analysis`: 52
- `ctf`: 50
- `implementation`: 48
- `frame-extraction`: 45
- `search`: 44

**Issues:**

- 1,050 unique strings for 1,065 skills = almost no normalization
- Ecosystem-specific terms used as capabilities (`doca`, `tao`, `azure`)
- No canonical taxonomy
- No mapping between similar capabilities
- "azure" as a capability is wrong — it's an ecosystem/platform, not a capability

### 3.8 Ecosystem Metadata

| Metric | Value |
|--------|-------|
| Empty `ecosystem_metadata` | 80/1,065 (7.5%) |
| Has license info | 1/1,065 (0.09%) |

Ecosystem metadata is mostly populated but contains only `detected_ecosystem` strings. No structured compatibility, version, or platform data.

### 3.9 Source Consistency

**18 repos in skills but missing from `sources` dict:**

`Alishahryar1/free-claude-code`, `zhaoxuya520/reverse-skill`, `atilaahmettaner/tradingview-mcp`, `adongwanai/AgentGuide`, `emilkowalski/skills`, `lidge-jun/opencodex`, `decolua/9router`, `HKUDS/Vibe-Trading`, `kaomei/stickman-video-director`, `tashfeenahmed/freellmapi`, `jakubkrehel/skills`, `autonomous-ai/autonomous-computer`, `bradautomates/claude-video`, `Jaycheng1103/chatgpt-video-editing-skills`, `chaseai-yt/grill-me-codex`, `browser-use/video-use`, `alchaincyf/nuwa-skill`, `brycewang-stanford/Auto-Research-Skills`

The `sources` dict was not updated when the second batch of repos was added.

### 3.10 License Coverage

**0.09%** — 1 out of 1,065 skills has any license information. This is a critical gap for redistribution.

---

## 4. What Must Be Preserved

1. **`registry.json` v2 format** — backward import compatibility required
2. **All 1,065 skill records** — no data loss
3. **Stable IDs** — UUID5 scheme is good, keep it
4. **The `sources` dict** — useful for provenance (but needs fixing)
5. **Existing field values** — summaries, domains, capabilities, tags (even if they need normalization)
6. **Repo+path provenance** — critical for traceability

---

## 5. Risk Assessment

### Performance Risks

- **O(n²) comparison:** 1,065 skills = 566,580 pairwise pairs. At 1ms/pair = 566 seconds. Needs candidate generation strategy.
- **Full JSON load:** 997KB is manageable now but will grow. Need indexed storage at ~5K+ skills.

### Code Quality Risks

- **No reproducibility:** Build scripts were ephemeral. Registry cannot be rebuilt from source.
- **No validation:** No schema validation was applied during build.
- **No tests:** Zero test coverage. Any change is untested.
- **No versioning:** No way to track what changed between registry versions.

### Migration Risks

- **Schema v2 → v3:** 228 records have string-format input/output shapes that need structural migration
- **18 missing source entries:** Need to backfill
- **39 broken summaries:** Need re-extraction from source repos
- **98.8% empty dependencies:** Need full re-extraction
- **0% license coverage:** Need bulk license detection

### Data Integrity Risks

- **Within-repo duplicates:** `openai-docs`, `applicationinsights-web-ts`, `entra-agent-id`, `nvidia-skill-finder` each appear twice from the same repo
- **Template skills:** 8 perspective skills from nuwa-skill are identical templates with different names
- **No content hashes:** Cannot detect upstream changes
- **No commit tracking:** Cannot determine staleness

---

## 6. Exact Phase 1 Plan

### Phase 1: Formal Domain Model + Schema v3 + Backward Importer

**Scope:**

1. **Define domain model** as Python dataclasses:
   - `Skill`, `SkillVersion`, `SkillSource`, `Repository`
   - `Capability`, `Domain`, `Tag`, `Dependency`
   - `RuntimeRequirement`, `CompatibilityProfile`
   - `InstallMethod`, `LicenseRecord`
   - `QualityAssessment`, `SecurityAssessment`
   - `SimilarityRecord`, `Relationship`
   - `ImportRecord`, `SourceSync`, `ExportProfile`

2. **Design schema v3** with all fields from spec Section 4

3. **Build backward importer** that reads current `registry.json` v2 and produces v3 records with:
   - Proper unknown/null handling
   - String input/output shapes converted to structured objects
   - Missing source entries backfilled
   - Provenance fields initialized (commit_sha=unknown, content_hash=unknown, etc.)

4. **Create `skillsbank/models/`** with Python package structure

5. **Create `skillsbank/schema/`** with JSON Schema for v3

6. **Create `skillsbank/importers/v2_importer.py`**

7. **Create tests** for import, schema validation, stable IDs

8. **Create `docs/DOMAIN_MODEL.md`** and `docs/REGISTRY_SCHEMA.md`

**Not in Phase 1:**
- SQLite/database (Phase 2)
- Parsers (Phase 4)
- Duplicate detection (Phase 6)
- Search (Phase 11)
- CLI (Phase 23)
- API (Phase 21)

**Estimated files to create:** ~15

---

## 7. Summary Statistics

| Metric | Value |
|--------|-------|
| Total skills | 1,065 |
| Total repos | 36 (18 in sources dict) |
| Duplicate IDs | 0 |
| Duplicate names | 11 groups |
| Within-repo duplicates | 4 |
| Content-identical skills | 6 groups |
| Broken summaries | 39 |
| String-format I/O shapes | 228 (21.4%) |
| Empty dependencies | 98.8% |
| License coverage | 0.09% |
| Unique capabilities | 1,050 (no taxonomy) |
| Generic "general" domain | 84 skills |
| Security skills w/o security caps | 47 |
| Provenance fields present | 0% |
| Reproducible build | No |
| Test coverage | 0% |
| Documentation | 0 files |
| Performance at 1K skills | 566K pairs for full comparison |

---

*End of Phase 0 Audit*
