"""JSON Schema generation from Pydantic v2 models."""

from __future__ import annotations

import json
from pathlib import Path

from skillsbank.models.registry import Registry


def generate_schema(output_path: str | Path | None = None) -> dict:
    """Generate JSON Schema for the v3 Registry model.

    Args:
        output_path: If provided, write schema to this file.

    Returns:
        The schema dict.
    """
    schema = Registry.model_json_schema()

    # Add custom metadata
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "SkillsBank Registry v3"
    schema["description"] = (
        "SkillsBank universal agent-skill registry schema v3. "
        "Contains skill identities, versions, repositories, and relationships."
    )

    if output_path is not None:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(schema, f, indent=2)

    return schema


if __name__ == "__main__":
    schema = generate_schema("skillsbank/schema/registry_v3.schema.json")
    print(f"Schema generated with {len(schema.get('definitions', {}))} definitions")
