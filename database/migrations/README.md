# Database Migrations

Simple versioned SQL migrations for PostgreSQL. No ORM dependencies.

## Usage

```bash
# Apply all pending migrations
python -m database.migrate

# Check migration status
python -m database.migrate --status

# Rollback last migration (if .down.sql exists)
python -m database.migrate --rollback 1
```

## Creating Migrations

1. Create a numbered SQL file in this directory:
   ```
   002_feature_name.sql
   ```

2. Optionally create a rollback file:
   ```
   002_feature_name.down.sql
   ```

## Naming Convention

```
{version}_{name}.sql       # Up migration
{version}_{name}.down.sql  # Down migration (optional)
```

- **version**: 3-digit zero-padded number (001, 002, 003)
- **name**: snake_case description

## Migration Tracking

Applied migrations are tracked in the `schema_migrations` table:

```sql
CREATE TABLE schema_migrations (
    version TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Current Migrations

| Version | Name | Description |
|---------|------|-------------|
| 001 | council_members | Council members + sponsorships tables |

## Guidelines

1. **Atomic**: Each migration runs in a single transaction
2. **Idempotent**: Use `IF NOT EXISTS` / `IF EXISTS` where possible
3. **Forward-only**: Prefer new columns over altering existing ones
4. **Documented**: Include comments explaining design decisions
5. **Tested**: Test on VPS before production deploy

## Rollback Safety

Not all migrations can be safely rolled back:
- Adding columns: Safe to rollback (drop column)
- Dropping columns: **Cannot rollback** (data lost)
- Data migrations: Depend on implementation

If a migration cannot be rolled back, don't create a `.down.sql` file.
