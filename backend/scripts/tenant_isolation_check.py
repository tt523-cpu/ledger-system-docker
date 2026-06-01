import json

from sqlalchemy import text

from app.core.database import SessionLocal


def run_check() -> dict:
    db = SessionLocal()
    try:
        checks = {}

        checks["platform_without_tenant"] = int(
            db.execute(text("select count(1) from platforms where tenant_id is null")).scalar_one() or 0
        )
        checks["account_without_tenant"] = int(
            db.execute(text("select count(1) from accounts where tenant_id is null")).scalar_one() or 0
        )
        checks["entry_type_without_tenant"] = int(
            db.execute(text("select count(1) from entry_types where tenant_id is null")).scalar_one() or 0
        )

        checks["cross_tenant_account_snapshot"] = int(
            db.execute(
                text(
                    """
                    select count(1)
                    from account_snapshots s
                    join accounts a on a.id = s.account_id
                    join user_tenant_access uta on uta.user_id = s.operator_id
                    where a.tenant_id <> uta.tenant_id
                    """
                )
            ).scalar_one()
            or 0
        )

        checks["orphan_user_tenant_access"] = int(
            db.execute(
                text(
                    """
                    select count(1)
                    from user_tenant_access uta
                    left join users u on u.id = uta.user_id
                    left join tenants t on t.id = uta.tenant_id
                    where u.id is null or t.id is null
                    """
                )
            ).scalar_one()
            or 0
        )

        checks["orphan_tenant_platform_access"] = int(
            db.execute(
                text(
                    """
                    select count(1)
                    from tenant_platform_access tpa
                    left join tenants t on t.id = tpa.tenant_id
                    left join platforms p on p.id = tpa.platform_id
                    where t.id is null or p.id is null
                    """
                )
            ).scalar_one()
            or 0
        )

        total_issues = sum(checks.values())
        return {"ok": total_issues == 0, "total_issues": total_issues, "checks": checks}
    finally:
        db.close()


if __name__ == "__main__":
    print(json.dumps(run_check(), ensure_ascii=False, indent=2))
