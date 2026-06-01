# RUNBOOK

## 1. Daily Operations

- Check service status:
  - `docker compose --env-file .env.prod ps`
- Check backend logs:
  - `docker compose --env-file .env.prod logs --tail=200 backend`
- Check DB health:
  - `docker compose --env-file .env.prod ps db`

## 2. Safe Update Procedure

1. Pull latest code:
   - `git pull --ff-only origin main`
2. Rebuild and restart services:
   - `docker compose --env-file .env.prod up -d --build`
3. Run migrations:
   - `docker compose --env-file .env.prod exec backend alembic upgrade head`
4. Restart app services:
   - `docker compose --env-file .env.prod restart backend frontend`
5. Smoke checks:
   - `curl -s http://127.0.0.1:8000/health`
   - Login and verify tenant list page loads

## 3. Rollback Procedure

1. Find previous commit:
   - `git log --oneline -20`
2. Reset working tree to target commit:
   - `git checkout <commit_sha>`
3. Rebuild and restart:
   - `docker compose --env-file .env.prod up -d --build`
4. If migration is incompatible, restore DB from backup file.

## 4. Backup and Restore Drill

- Export full backup from UI or API.
- Restore into test environment first.
- Verify these tables after restore:
  - `tenants`
  - `user_tenant_access`
  - `tenant_platform_access`
  - `accounts`
  - `entry_types`
  - `entry_type_settings`
  - `role_module_permissions`

## 5. Tenant Deletion Procedure

1. Run tenant precheck in UI (shows table-by-table counts).
2. If any business tables are non-zero, clean tenant data first.
3. Delete tenant from super-admin tenant page.
4. Confirm tenant removed and access accounts deleted.

## 6. Incident Triage Shortcuts

- `405 Method Not Allowed` on a new action:
  - Usually backend container running old image; rebuild backend.
- "Delete success but row still exists":
  - Verify response payload and backend logs for FK errors.
- Cross-tenant display issue:
  - Run tenant isolation inspection script in section 7.

## 7. Isolation Inspection Script

- Run:
  - `docker compose --env-file .env.prod exec backend python scripts/tenant_isolation_check.py`
- Output:
  - JSON summary with issue counts and sample rows.
