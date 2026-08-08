"""add_composite_indexes

Revision ID: 446836f78921
Revises: 726208d6018a
Create Date: 2026-08-08 02:12:47.040054

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "446836f78921"
down_revision: str | Sequence[str] | None = "726208d6018a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add composite indexes for common query patterns."""
    op.create_index("ix_versions_domain_repo", "versions", ["domain_primary", "source_repo"])
    op.create_index("ix_versions_skill_version", "versions", ["skill_id", "version_id"])
    op.create_index("ix_capabilities_version_name", "capabilities", ["version_id_fk", "name"])
    op.create_index("ix_tags_version_name", "tags", ["version_id_fk", "name"])


def downgrade() -> None:
    """Remove composite indexes."""
    op.drop_index("ix_tags_version_name", "tags")
    op.drop_index("ix_capabilities_version_name", "capabilities")
    op.drop_index("ix_versions_skill_version", "versions")
    op.drop_index("ix_versions_domain_repo", "versions")
