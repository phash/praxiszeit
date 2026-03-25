# FIXME: Auth Middleware Validations (apply after RLS agent changes)

These fixes must be applied to `backend/app/middleware/auth.py` after the parallel RLS agent
has finished its changes to that file.

## Fix H-2: Validate JWT `tid` Against DB User's `tenant_id`

After the user is loaded from the database, add a check that the `tid` claim in the JWT
matches the user's actual `tenant_id` in the database. This prevents stale tokens from
working after a user is moved to a different tenant.

```python
jwt_tid = payload.get("tid")
db_tid = str(user.tenant_id) if user.tenant_id else None
if jwt_tid and db_tid and jwt_tid != db_tid:
    raise HTTPException(status_code=401, detail="Token tenant mismatch. Bitte erneut anmelden.")
tenant_id = db_tid  # Always use database truth
```

## Fix M-4: Check `Tenant.is_active` During Auth

After loading the user, also check that the user's tenant is still active. This ensures that
deactivated tenants cannot continue to authenticate.

```python
from app.models.tenant import Tenant
if user.tenant_id:
    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
    if tenant and not tenant.is_active:
        raise HTTPException(status_code=403, detail="Tenant deaktiviert")
```

Both checks should be inserted in the `get_current_user` dependency (or equivalent) in
`middleware/auth.py`, right after the user record is fetched from the database and before
any further processing.
