# [Implementation Plan] Alembic Programmatic Auto-Migration Integration (Method A)

This plan details the implementation of a robust, production-grade database migration system using **Alembic**. It transitions the project from unsafe, manual raw SQL `ALTER TABLE` scripts inside `main.py` to a database-agnostic, version-controlled programmatic migration engine that runs automatically on FastAPI application startup.

## User Review Required

> [!IMPORTANT]
> **Database Backups:**
> Although the programmatic auto-migration is designed to be extremely safe, we highly recommend making a copy/backup of your `backend/stockauto.db` before applying this upgrade in production environments.
>
> **No Manual DB Commands Needed:**
> Once this is implemented, you do NOT need to run `alembic upgrade head` in your shell manually. The server launcher (`python run.py`) will automatically execute migrations in the background upon startup.

## Proposed Changes

We will clean up the manual schema alteration codes inside `app/main.py`, restructure the Alembic migration history to have a clean baseline migration, and write a helper script to automatically upgrade or stamp the database on startup.

---

### [Component 1] Baseline Migration Schema

#### ⚙️ [DELETE] [e10797b8bd90_initial.py](file:///d:/dev/workspace/stockAuto/backend/alembic/versions/e10797b8bd90_initial.py)
We will remove the existing fragmented migration and replace it with a clean, comprehensive baseline migration representing the entire current database structure.

#### ⚙️ [NEW] [001_baseline_migration.py](file:///d:/dev/workspace/stockAuto/backend/alembic/versions/001_baseline_migration.py)
We will define a new baseline migration script that defines the creation of all existing tables:
* `users`
* `user_settings`
* `trade_logs`
* `holdings`
* `action_logs`
* `watch_lists`
* `stock_translations`

This baseline will be used to initialize clean, empty databases, while existing databases will be programmatically stamped to bypass it.

---

### [Component 2] Programmatic Migration Bootstrapper

#### ⚙️ [NEW] [migrator.py](file:///d:/dev/workspace/stockAuto/backend/app/core/migrator.py)
We will build a high-reliability helper module `app/core/migrator.py` to handle the programmatic execution of migrations on startup.
It will implement the following logic:
1. **Detect Existing Databases:** Check if the `users` table already exists in the database.
2. **Check Migration Version State:** Check if the `alembic_version` table exists.
3. **Smart Bootstrapping:**
   * If `users` exists but `alembic_version` does NOT: This is an existing pre-Alembic database. Run programmatic `alembic stamp head` so Alembic marks the schema as up-to-date without attempting to re-create the tables.
   * If `users` does NOT exist: This is a completely fresh database. Run programmatic `alembic upgrade head` to run all migration scripts from scratch.
   * If `alembic_version` exists: Run programmatic `alembic upgrade head` to apply any new pending migrations.

---

### [Component 3] Uvicorn Startup Integration

#### ⚙️ [MODIFY] [main.py](file:///d:/dev/workspace/stockAuto/backend/app/main.py)
* **Remove Hacks:** Delete `Base.metadata.create_all(bind=engine)` and the manual `migrate_db_columns()` function.
* **Integrate Bootstrapper:** Import `run_migrations_programmatically` from `app.core.migrator` and call it right at startup, before starting the background scheduler.

---

## Verification Plan

### Automated Verification
1. **Clean DB Setup Test:**
   * Rename `stockauto.db` to `stockauto.db.bak`.
   * Start the server using `python run.py local`.
   * Verify that `stockauto.db` is automatically created from scratch by running the Alembic migration history, containing all 7 tables and standard SQLite structures.
2. **Existing DB Upgrade Test:**
   * Restore `stockauto.db.bak` to `stockauto.db`.
   * Start the server using `python run.py local`.
   * Verify that the backend successfully detects the existing database, stamps it to `head` in `alembic_version` without raising any "Table already exists" errors, and boots up normally.

### Manual Verification
* Access the Next.js frontend dashboard and ensure all data (watchlist, settings, holdings) is fetched and displayed correctly from the existing database.
