# SkillsBank Registry Schema v3

**Version:** 3.0.0
**Generated from:** Pydantic v2 models
**JSON Schema file:** `skillsbank/schema/registry_v3.schema.json`

## Top-Level Structure

```json
{
  "schema_version": "3.0.0",
  "generated_at": "2026-08-08T...",
  "skills": [Skill, ...],
  "versions": [SkillVersion, ...],
  "repositories": [Repository, ...],
  "relationships": [Relationship, ...],
  "similarities": [SimilarityRecord, ...],
  "total_skills": 1065,
  "total_versions": 1065,
  "total_repos": 36,
  "migrated_from": "registry_v2.0.0",
  "migration_notes": [...]
}
```

## Skill Object

```json
{
  "id": "6ea34e93-d625-5ec2-b9c5-a4a7f414622e",
  "canonical_key": "mattpocock/skills/code-review",
  "name": "code-review",
  "display_name": null,
  "aliases": [],
  "lifecycle": "unknown",
  "is_current": true,
  "primary_source": {"value": "mattpocock/skills", "source": "imported", "confidence": null, "set_at": null},
  "primary_path": {"value": "skills/engineering/code-review/SKILL.md", "source": "imported", "confidence": null, "set_at": null},
  "first_seen_at": "2026-08-08T...",
  "last_updated_at": null,
  "metadata_quality": "COMPLETE",
  "version_count": 1,
  "current_version_id": null
}
```

## SkillVersion Object

```json
{
  "skill_id": "6ea34e93-d625-5ec2-b9c5-a4a7f414622e",
  "version_id": null,
  "source": {
    "repo": "mattpocock/skills",
    "owner": "mattpocock",
    "repo_url": "https://github.com/mattpocock/skills",
    "skill_path": "skills/engineering/code-review/SKILL.md",
    "commit_sha": null,
    "branch": null,
    "content_hash": null,
    "source_type": "github_repo",
    "upstream_created_at": null,
    "upstream_updated_at": null
  },
  "imported_at": "2026-08-08T...",
  "last_checked_at": null,
  "name": "code-review",
  "display_name": null,
  "summary": "Two-axis code review...",
  "long_description": null,
  "domain": {
    "primary": {"value": "code-review", "source": "imported"},
    "secondary": [],
    "confidence": null,
    "source": "unknown",
    "quality": "UNKNOWN"
  },
  "capabilities": [
    {"name": "parallel_sub_agent_review", "canonical": null, "taxonomy_path": null, "confidence": null}
  ],
  "tags": [
    {"name": "review", "source": "imported"}
  ],
  "input_shape": {
    "format": "natural_language",
    "required": [],
    "optional": [],
    "json_schema": null,
    "quality": "PARTIAL"
  },
  "output_shape": {
    "format": "markdown",
    "json_schema": null,
    "quality": "PARTIAL"
  },
  "declared_dependencies": [],
  "inferred_dependencies": [],
  "runtime_requirements": {
    "tools": [],
    "apis": [],
    "packages": [],
    "env_vars": [],
    "runtimes": [],
    "shell_required": false,
    "filesystem_write": false,
    "network_required": false,
    "quality": "UNKNOWN"
  },
  "compatibility": {
    "entries": [],
    "invocation_type": null,
    "skill_md_format": false,
    "mcp_compatible": false,
    "quality": "UNKNOWN"
  },
  "install_methods": [],
  "quality": {
    "overall_score": null,
    "dimensions": [],
    "metadata_completeness": "COMPLETE",
    "documentation_quality": "COMPLETE",
    "specificity": "UNKNOWN",
    "portability": "UNKNOWN",
    "dependency_clarity": "UNKNOWN",
    "maintainability": "UNKNOWN",
    "testability": "UNKNOWN",
    "extraction_confidence": "UNKNOWN"
  },
  "security": {
    "risk_level": "UNKNOWN",
    "risk_factors": [],
    "shell_execution": false,
    "filesystem_access": false,
    "network_access": false,
    "browser_automation": false,
    "credential_requirements": [],
    "package_installation": false,
    "destructive_potential": false,
    "security_tooling": false,
    "review_status": "not_reviewed"
  },
  "license": {
    "license_type": null,
    "detected_source": null,
    "status": "unknown",
    "redistributable": null,
    "modifiable": null,
    "commercial_restrictions": null,
    "attribution_required": null,
    "verified": false,
    "notes": null
  },
  "ecosystem_metadata": {},
  "migration": {
    "imported_from": "registry_v2",
    "imported_at": "2026-08-08T...",
    "original_values": {},
    "normalization_notes": [],
    "parser_version": null,
    "extractor_version": null
  }
}
```

## Repository Object

```json
{
  "id": "mattpocock/skills",
  "url": "https://github.com/mattpocock/skills",
  "owner": "mattpocock",
  "name": "skills",
  "source_type": "github_repo",
  "license": {"license_type": null, "status": "unknown"},
  "default_branch": null,
  "description": null,
  "ecosystem": null,
  "parser_compatibility": null,
  "last_successful_sync": null,
  "sync_errors": [],
  "snapshots": [],
  "skill_count": 20
}
```

## Migration from v2

The v2 importer (`skillsbank/importers/v2_importer.py`) handles:
- Preserving all original v2 values in `migration.original_values`
- Normalizing malformed I/O shapes (228 records had raw strings)
- Flagging broken summaries (43 records with markdown artifacts)
- Backfilling 18 missing repository entries
- Preserving stable UUID5 IDs
- Explicit unknowns for: commit_sha, content_hash, branch, upstream dates, license, risk level, compatibility

## Backward Compatibility

The original `registry.json` v2 is preserved as immutable. The v3 format is a separate artifact (`registry.v3.json`). The v2 importer can be re-run at any time.
