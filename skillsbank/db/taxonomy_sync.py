"""Phase 4: Apply capability taxonomy normalization to SQLite database."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from skillsbank.taxonomy import classify_capability


def normalize_db_capabilities(session: Session) -> dict[str, int]:
    """Normalize all capabilities in the database, adding canonical/category/taxonomy_path.

    Returns stats: {normalized, already_normalized, errors}
    """
    stats = {"normalized": 0, "already_normalized": 0, "errors": 0}

    rows = session.execute(text("SELECT id, name, canonical, taxonomy_path FROM capabilities")).fetchall()

    for row_id, name, existing_canonical, existing_path in rows:
        try:
            canonical, _category, taxonomy_path = classify_capability(name)

            # Update if canonical/taxonomy_path not set or different
            if existing_canonical != canonical or existing_path != taxonomy_path:
                session.execute(
                    text("UPDATE capabilities SET canonical = :canonical, taxonomy_path = :path WHERE id = :id"),
                    {"canonical": canonical, "path": taxonomy_path, "id": row_id},
                )
                stats["normalized"] += 1
            else:
                stats["already_normalized"] += 1
        except Exception:
            stats["errors"] += 1

    session.commit()
    return stats


def get_category_distribution(session: Session) -> dict[str, int]:
    """Get capability category distribution from the database."""
    rows = session.execute(
        text(
            """
            SELECT taxonomy_path, COUNT(*) as cnt
            FROM capabilities
            WHERE taxonomy_path IS NOT NULL
            GROUP BY taxonomy_path
            ORDER BY cnt DESC
            """
        )
    ).fetchall()

    from collections import Counter

    category_counts: Counter[str] = Counter()
    for path, count in rows:
        if path and "/" in path:
            category = path.split("/")[0]
            category_counts[category] += count
        else:
            category_counts["uncategorized"] += count

    return dict(category_counts.most_common())
