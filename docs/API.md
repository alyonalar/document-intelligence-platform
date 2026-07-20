# API Reference

OpenAPI docs are available at `/docs` when the app is running.

## Health

- `GET /health`

## Documents

- `GET /api/documents/{document_id}`
- `GET /documents/`
- `GET /documents/{document_id}`
- `GET /documents/{document_id}/file`
- `GET /documents/{document_id}/thumbnail/{page_number}`
- `GET /documents/{document_id}/export.md`
- `GET /documents/{document_id}/export.docx`
- `GET /documents/{document_id}/export.pdf`
- `GET /documents/{document_id}/view`
- `GET /documents/{document_id}/ask`
- `POST /documents/upload`
- `POST /documents/{document_id}/generate-summary`
- `POST /documents/{document_id}/reindex`
- `POST /documents/{document_id}/recompute-insights`
- `POST /documents/{document_id}/recompute-intelligence`
- `POST /documents/{document_id}/retry`
- `POST /documents/reindex-all`
- `POST /documents/recompute-insights-all`
- `POST /documents/{document_id}/delete`

## Search

- `GET /api/documents/search`

## QA

- `POST /api/documents/{document_id}/ask`
- `POST /api/workspace/ask`

## Compare

- `POST /api/documents/compare`
- `GET /workspace/compare`

## Intelligence

- `POST /api/documents/{document_id}/intelligence/recompute`
- `POST /api/intelligence/recompute-all`
- `GET /api/intelligence/summary`
- `GET /intelligence`
- `GET /graph`
- `POST /graph/rebuild`

## Entities

- `GET /api/documents/{document_id}/entities`

## Relations

- `GET /api/documents/{document_id}/relations`
- `GET /api/documents/{document_id}/graph`

## Obligations

- `GET /api/documents/{document_id}/obligations`
- `GET /api/obligations`
- `PATCH /api/obligations/{obligation_id}/status`
- `GET /api/obligations/summary`
- `GET /obligations`
- `POST /obligations/{obligation_id}/status`

## Risks

- `GET /api/documents/{document_id}/risks`
- `GET /api/risks`
- `GET /api/risks/summary`
- `GET /risks`

## Actions

- `GET /api/actions`
- `POST /api/actions/{action_key}/status`
- `POST /api/actions/{action_key}/note`
- `GET /actions`
- `GET /actions/export.md`
- `POST /actions/{action_key}/status`
- `POST /actions/{action_key}/note`

## Jobs

- `GET /api/jobs`
- `GET /api/jobs/{job_id}`
- `GET /api/documents/{document_id}/jobs`
- `POST /api/documents/{document_id}/process`
- `POST /api/jobs/{job_id}/retry`

## Workspace

- `POST /workspace`
- `GET /workspace`
- `GET /workspace/ask`

## Collections

- `POST /collections/create`
- `GET /collections/{collection_id}`
- `GET /collections/{collection_id}/export.md`
- `GET /collections/{collection_id}/export.docx`
- `GET /collections/{collection_id}/export.pdf`
- `POST /collections/{collection_id}/update`
- `POST /collections/{collection_id}/remove-document`
- `POST /collections/{collection_id}/delete`
- `POST /collections/add-documents`

## History

- `GET /history`
- `GET /history/export.md`
- `POST /history/{interaction_id}/delete`

## Built-In Documentation

- `GET /docs`
- `GET /redoc`
- `GET /openapi.json`
