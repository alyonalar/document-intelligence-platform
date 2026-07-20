# Database

The project uses SQLite through SQLModel and Alembic. Alembic is the schema source of truth; application startup does not call `create_all()`.

## Tables

- `collection`
- `collectiondocumentlink`
- `document`
- `processingjob`
- `actionitemstate`
- `qainteraction`
- `documententity`
- `documentrelation`
- `documentobligation`
- `documentrisk`
- `entityalias`

## Document Status Fields

- `processing_status`
- `processing_error`
- `indexed_chunks`
- `intelligence_status`
- `intelligence_error`
- `intelligence_processed_at`

## Migrations

Apply migrations:

```powershell
alembic upgrade head
```

Create a migration after model changes:

```powershell
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

Migration history includes initial schema, collections, QA history sources, processing status, processing jobs, document insights, action item states/notes/due date override, processing job attempts, document intelligence tables, and later removal of deprecated intelligence tables.

SQLite foreign-key enforcement is enabled on every application connection. Document-owned rows use cascade deletion, while the lifecycle service also performs explicit cleanup for databases created before the cascade migration.
