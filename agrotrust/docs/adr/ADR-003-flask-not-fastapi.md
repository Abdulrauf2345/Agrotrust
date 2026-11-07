# ADR-003: Flask API layer, not FastAPI

**Status:** Accepted (sandbox constraint)

## Context
The spec calls for FastAPI + Pydantic v2 for request/response validation and OpenAPI
generation. Neither `fastapi` nor `pydantic` is installed in this sandbox, and there is no
network access to install them. Flask *is* installed.

## Decision
Build `api/app.py` on Flask, with:
- A hand-written `DomainError -> HTTP status/JSON` mapping (`@app.errorhandler(DomainError)`)
  doing the job Pydantic/FastAPI's exception handling would do automatically.
- Manual JSON body parsing and field extraction (`json_body()` helper) in place of Pydantic
  request models. Every module's service methods already validate their own inputs
  (`ValidationFailed` on bad data), so the API layer's job is thin: parse JSON, call the
  service, serialize the result - the validation logic itself already lives in the right place
  and does not need to be duplicated in a request-model layer.
- No auto-generated OpenAPI spec (FastAPI's biggest structural advantage). `docs/api/` would
  hold a hand-written OpenAPI 3 document in a real deployment; it is not attempted here since
  keeping it in sync by hand across ~20 modules is not a good use of effort in a sandbox that
  cannot even serve interactive docs.

## Consequences
- Request validation errors surface as the service layer's own `ValidationFailed`
  (`details` dict included), not Pydantic's structured per-field error format. Less polished,
  but the information content (what's wrong, on which field) is the same.
- Migrating to FastAPI later is mechanical: each Flask route becomes a FastAPI path operation,
  each `json_body()` + manual field access becomes a Pydantic request model, and
  `DomainError.http_status`/`.code`/`.details` map directly onto FastAPI's
  `HTTPException`/custom exception handlers - the module layer underneath does not change at
  all, which is the point of keeping business logic out of the API layer in the first place.
