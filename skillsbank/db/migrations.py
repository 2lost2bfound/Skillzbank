"""Programmatic Alembic migration support for SkillsBank.

Provides ``migrate_to_head()`` so an installed wheel can evolve
an existing database without requiring the ``alembic`` CLI.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command as alembic_command
from alembic.config import Config


def _alembic_cfg(db_url: str | None = None) -> Config:
    """Build an Alembic Config pointing at the bundled migrations."""
    # Locate alembic.ini next to the package root
    pkg_dir = Path(__file__).resolve().parent.parent  # skillsbank/
    ini_path = pkg_dir / "alembic.ini"
    if not ini_path.exists():
        # Fallback: search upward
        for parent in pkg_dir.parents:
            candidate = parent / "alembic.ini"
            if candidate.exists():
                ini_path = candidate
                break

    cfg = Config(str(ini_path))
    if db_url:
        cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def migrate_to_head(db_url: str | None = None) -> None:
    """Apply all pending Alembic migrations to *db_url*.

    If *db_url* is ``None`` the URL from ``alembic.ini`` is used.
    """
    cfg = _alembic_cfg(db_url)
    alembic_command.upgrade(cfg, "head")


def migrate_down(db_url: str, revision: str = "-1") -> None:
    """Downgrade *db_url* by one revision (or to a specific revision)."""
    cfg = _alembic_cfg(db_url)
    alembic_command.downgrade(cfg, revision)


def current_revision(db_url: str | None = None) -> str | None:
    """Return the current Alembic revision for *db_url*, or ``None``."""
    cfg = _alembic_cfg(db_url)
    # command.current writes to stdout; use a script wrapper
    import contextlib
    from io import StringIO

    buf = StringIO()
    with contextlib.redirect_stdout(buf):
        alembic_command.current(cfg, verbose=False)
    output = buf.getvalue().strip()
    if output and "(head)" in output:
        return output.split(" ")[0]
    return output.split(" ")[0] if output else None
