"""
Database layer: connection handling, schema creation, and migrations.

Migration safety note
----------------------
Earlier versions of this app used `ALTER TABLE projects RENAME TO
projects_old; ...; DROP TABLE projects_old;` to add the `user_id` column
while `PRAGMA foreign_keys = ON` was active on the same connection. SQLite's
RENAME TABLE, when foreign keys are enabled, rewrites *other* tables'
foreign-key clauses that pointed at the renamed table -- so
timesheet_entries.project_id silently became "REFERENCES projects_old(id)".
The subsequent DROP TABLE projects_old then failed with
"FOREIGN KEY constraint failed" (rows in timesheet_entries still referenced
it), and -- because that DROP never happened -- the bad reference to
projects_old was left permanently baked into timesheet_entries' schema.

The fix has two parts:
  1. Never enable `foreign_keys` on the connection used for migrations, and
     set `PRAGMA legacy_alter_table = ON` around any RENAME, so ALTER TABLE
     never rewrites other tables' schema text.
  2. Self-heal any database that already hit the bug: detect a leftover
     `projects_old` table and/or a `timesheet_entries` table whose stored
     schema mentions `projects_old`, and repair both before continuing.
"""
import sqlite3

from flask import g

from config import DB_PATH


def get_db():
    """Per-request connection (Flask app context). Foreign keys ON here --
    by request time the schema is stable, so normal FK enforcement is safe
    and desirable."""
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _table_exists(db, name):
    return (
        db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
        ).fetchone()
        is not None
    )


def _table_sql(db, name):
    row = db.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone()
    return row["sql"] if row else None


def _repair_projects_old_leftover(db):
    """
    Undo/finish a migration that was interrupted after RENAME+CREATE+INSERT
    but before the final DROP TABLE projects_old (see module docstring).
    """
    if not _table_exists(db, "projects_old"):
        return

    if _table_exists(db, "projects"):
        # The new-schema `projects` table was already created and populated
        # before the old run crashed on the DROP -- just finish that drop.
        # legacy_alter_table isn't needed for a plain DROP, but foreign_keys
        # is guaranteed OFF on this connection so it can't fail the same way.
        db.execute("DROP TABLE projects_old")
    else:
        # `projects` doesn't exist at all (shouldn't normally happen) --
        # simplest recovery is to put the old table back under its name.
        db.execute("PRAGMA legacy_alter_table = ON")
        db.execute("ALTER TABLE projects_old RENAME TO projects")
        db.execute("PRAGMA legacy_alter_table = OFF")
    db.commit()


def _repair_timesheet_entries_fk(db):
    """
    If timesheet_entries' stored schema references anything other than the
    current `projects` table (i.e. it still says "projects_old" from the
    bug above), rebuild it with a correct foreign key, preserving all rows.
    """
    sql = _table_sql(db, "timesheet_entries")
    if sql is None or "projects_old" not in sql:
        return

    db.execute("PRAGMA legacy_alter_table = ON")
    db.executescript(
        """
        ALTER TABLE timesheet_entries RENAME TO timesheet_entries_old;
        CREATE TABLE timesheet_entries (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id  INTEGER NOT NULL REFERENCES projects(id),
            entry_date  TEXT NOT NULL,
            week_start  TEXT NOT NULL,
            hours       REAL NOT NULL CHECK (hours >= 0 AND hours <= 8),
            notes       TEXT DEFAULT '',
            UNIQUE(project_id, entry_date)
        );
        INSERT INTO timesheet_entries (id, project_id, entry_date, week_start, hours, notes)
            SELECT id, project_id, entry_date, week_start, hours, notes FROM timesheet_entries_old;
        DROP TABLE timesheet_entries_old;
        """
    )
    db.execute("PRAGMA legacy_alter_table = OFF")
    db.commit()


def _migrate_projects_add_user_id(db):
    """Add the user_id column to a pre-authentication `projects` table."""
    db.execute("PRAGMA legacy_alter_table = ON")
    db.executescript(
        """
        ALTER TABLE projects RENAME TO projects_old;
        CREATE TABLE projects (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name    TEXT NOT NULL,
            active  INTEGER NOT NULL DEFAULT 1,
            UNIQUE(user_id, name COLLATE NOCASE)
        );
        INSERT INTO projects (id, user_id, name, active)
            SELECT id, NULL, name, active FROM projects_old;
        DROP TABLE projects_old;
        """
    )
    db.execute("PRAGMA legacy_alter_table = OFF")
    db.commit()


def init_db():
    """
    Create the schema on a brand-new database, or migrate/repair an
    existing one. Runs on a dedicated connection that deliberately never
    enables `PRAGMA foreign_keys` -- see the module docstring.
    """
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            email                 TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash         TEXT NOT NULL,
            first_name            TEXT NOT NULL DEFAULT '',
            last_name             TEXT NOT NULL DEFAULT '',
            mobile_phone          TEXT NOT NULL DEFAULT '',
            entity_name           TEXT NOT NULL DEFAULT '',
            must_change_password  INTEGER NOT NULL DEFAULT 1,
            created_at            TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    db.commit()

    # Self-heal a database that hit the old RENAME/FK bug before continuing.
    _repair_projects_old_leftover(db)

    if not _table_exists(db, "projects"):
        db.execute(
            """
            CREATE TABLE projects (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                name    TEXT NOT NULL,
                active  INTEGER NOT NULL DEFAULT 1,
                UNIQUE(user_id, name COLLATE NOCASE)
            )
            """
        )
        db.commit()
    else:
        cols = [r["name"] for r in db.execute("PRAGMA table_info(projects)").fetchall()]
        if "user_id" not in cols:
            # Upgrading a pre-authentication database: give every project a
            # (nullable, for now) owner column. Existing rows become
            # "orphaned" (user_id IS NULL) and are handed to whoever
            # registers/logs in first -- see auth.adopt_orphan_projects_if_first_user().
            _migrate_projects_add_user_id(db)

    if not _table_exists(db, "timesheet_entries"):
        db.execute(
            """
            CREATE TABLE timesheet_entries (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id  INTEGER NOT NULL REFERENCES projects(id),
                entry_date  TEXT NOT NULL,          -- ISO date, always a Monday..Sunday date
                week_start  TEXT NOT NULL,          -- ISO date of the Monday that starts the week
                hours       REAL NOT NULL CHECK (hours >= 0 AND hours <= 8),
                notes       TEXT DEFAULT '',
                UNIQUE(project_id, entry_date)
            )
            """
        )
        db.commit()
    else:
        # Repair a timesheet_entries table left pointing at "projects_old"
        # by a previous, interrupted migration attempt (see module docstring).
        _repair_timesheet_entries_fk(db)

    db.execute("CREATE INDEX IF NOT EXISTS idx_entries_week ON timesheet_entries(week_start)")
    db.commit()

    # Seed sample projects only for a genuinely brand-new install (no users,
    # no projects yet). They start "orphaned" and are adopted by the first
    # person who registers, so a fresh install still has something to look at.
    no_users = db.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"] == 0
    no_projects = db.execute("SELECT COUNT(*) AS c FROM projects").fetchone()["c"] == 0
    if no_users and no_projects:
        db.executemany(
            "INSERT INTO projects (user_id, name) VALUES (NULL, ?)",
            [("Internal",), ("Project Alpha",), ("Project Beta",)],
        )
        db.commit()
    db.close()
