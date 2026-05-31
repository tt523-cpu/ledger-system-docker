from datetime import date
from io import BytesIO

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_accessible_platform_ids, get_current_tenant_id, require_module, require_roles
from app.models.entities import AccountSnapshot, AuditLog, Category, DailySummary, PaymentMethod, Platform, Shift, Tenant, TenantPlatformAccess, Transaction, User
from app.models.enums import UserRole


router = APIRouter(prefix="/exports", tags=["exports"])


def apply_money_format(ws, cols: list[int], start_row: int = 2):
    for r in range(start_row, ws.max_row + 1):
        for c in cols:
            ws.cell(row=r, column=c).number_format = "0.00"


def _scoped_platform_ids(db: Session, current_user: User) -> list[int] | None:
    if current_user.role == UserRole.SUPER_ADMIN.value:
        return None
    return get_accessible_platform_ids(db, current_user)


def _tenant_select(model, tenant_id: int | None):
    stmt = select(model)
    if tenant_id is not None:
        stmt = stmt.where(model.tenant_id == tenant_id)
    return stmt


@router.get("/daily-excel")
def export_daily_excel(
    bill_date: str,
    shift_id: int | None = None,
    platform_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module("reports.query")),
):
    allowed = _scoped_platform_ids(db, current_user)
    tenant_id = get_current_tenant_id(db, current_user)
    if allowed == []:
        allowed = [-1]
    wb = Workbook()
    ws = wb.active
    ws.title = "日报表"
    ws.append(["日期", "班次", "平台", "充值", "支出", "净营业"])

    stmt = select(DailySummary).where(DailySummary.bill_date == bill_date)
    if allowed is not None:
        stmt = stmt.where(DailySummary.platform_id.in_(allowed))
    if shift_id:
        stmt = stmt.where(DailySummary.shift_id == shift_id)
    if platform_id:
        stmt = stmt.where(DailySummary.platform_id == platform_id)
    rows = db.execute(stmt.order_by(DailySummary.shift_id.asc(), DailySummary.platform_id.asc())).scalars().all()
    platform_stmt = select(Platform.id, Platform.name)
    shift_stmt = select(Shift.id, Shift.name)
    if tenant_id is not None:
        platform_stmt = platform_stmt.where(Platform.tenant_id == tenant_id)
        shift_stmt = shift_stmt.where(Shift.tenant_id == tenant_id)
    platform_map = {r[0]: r[1] for r in db.execute(platform_stmt).all()}
    shift_map = {r[0]: r[1] for r in db.execute(shift_stmt).all()}

    for row in rows:
        ws.append([
            row.bill_date.isoformat(),
            shift_map.get(row.shift_id, row.shift_id),
            platform_map.get(row.platform_id, f"平台#{row.platform_id}"),
            float(row.total_income or 0),
            float(row.total_expense or 0),
            float(row.net_profit or 0),
        ])
    apply_money_format(ws, [4, 5, 6])

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    filename = f"daily-{bill_date}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/report-query-excel")
def export_report_query_excel(
    start_date: str,
    end_date: str,
    shift_id: int | None = None,
    platform_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module("reports.query")),
):
    allowed = _scoped_platform_ids(db, current_user)
    tenant_id = get_current_tenant_id(db, current_user)
    if allowed == []:
        allowed = [-1]
    wb = Workbook()
    ws = wb.active
    ws.title = "报表查询"
    ws.append(["日期", "班次", "平台", "充值", "支出", "净营业"])

    stmt = select(DailySummary).where(DailySummary.bill_date >= start_date, DailySummary.bill_date <= end_date)
    if allowed is not None:
        stmt = stmt.where(DailySummary.platform_id.in_(allowed))
    if shift_id:
        stmt = stmt.where(DailySummary.shift_id == shift_id)
    if platform_id:
        stmt = stmt.where(DailySummary.platform_id == platform_id)
    rows = db.execute(stmt.order_by(DailySummary.bill_date.asc(), DailySummary.shift_id.asc(), DailySummary.platform_id.asc())).scalars().all()
    platform_stmt = select(Platform.id, Platform.name)
    shift_stmt = select(Shift.id, Shift.name)
    if tenant_id is not None:
        platform_stmt = platform_stmt.where(Platform.tenant_id == tenant_id)
        shift_stmt = shift_stmt.where(Shift.tenant_id == tenant_id)
    platform_map = {r[0]: r[1] for r in db.execute(platform_stmt).all()}
    shift_map = {r[0]: r[1] for r in db.execute(shift_stmt).all()}

    category_map = {c.id: c.name for c in db.execute(_tenant_select(Category, tenant_id)).scalars().all()}
    row_expense_stmt = select(
        Transaction.bill_date,
        Transaction.shift_id,
        Transaction.platform_id,
        Transaction.category_id,
        Transaction.biz_type_label,
        func.sum(Transaction.amount),
    ).where(
        Transaction.bill_date >= start_date,
        Transaction.bill_date <= end_date,
        Transaction.type == "expense",
        Transaction.deleted_at.is_(None),
    )
    if allowed is not None:
        row_expense_stmt = row_expense_stmt.where(Transaction.platform_id.in_(allowed))
    if shift_id:
        row_expense_stmt = row_expense_stmt.where(Transaction.shift_id == shift_id)
    if platform_id:
        row_expense_stmt = row_expense_stmt.where(Transaction.platform_id == platform_id)
    row_expense_rows = db.execute(
        row_expense_stmt.group_by(
            Transaction.bill_date,
            Transaction.shift_id,
            Transaction.platform_id,
            Transaction.category_id,
            Transaction.biz_type_label,
        )
    ).all()
    expense_detail_map = {}
    for bill_date_val, shift_val, platform_val, category_id_val, biz_type_label_val, amount_sum in row_expense_rows:
        key = (bill_date_val.isoformat(), int(shift_val), int(platform_val))
        if category_id_val is None:
            item_name = (biz_type_label_val or "-").strip() or "-"
        else:
            item_name = category_map.get(category_id_val, f"项目#{category_id_val}")
        detail = f"{item_name}:{float(amount_sum or 0):.2f}"
        expense_detail_map.setdefault(key, []).append(detail)

    for row in rows:
        key = (row.bill_date.isoformat(), int(row.shift_id), int(row.platform_id))
        expense_details = "，".join(expense_detail_map.get(key, []))
        expense_cell = f"{float(row.total_expense):.2f}"
        if expense_details:
            expense_cell = f"{float(row.total_expense):.2f}（{expense_details}）"
        ws.append([
            row.bill_date.isoformat(),
            shift_map.get(row.shift_id, row.shift_id),
            platform_map.get(row.platform_id, f"平台#{row.platform_id}"),
            float(row.total_income or 0),
            expense_cell,
            float(row.net_profit or 0),
        ])
    apply_money_format(ws, [4, 6])

    ws_bal = wb.create_sheet("账户余额")
    ws_bal.append(["账户", "通道类型", "期初余额", "充值", "支出", "期末余额"])
    methods = db.execute(_tenant_select(PaymentMethod, tenant_id).where(PaymentMethod.status == "enabled")).scalars().all()
    total_opening = 0.0
    total_recharge = 0.0
    total_payout = 0.0
    total_closing = 0.0
    for pm in methods:
        before_row = db.execute(
            select(func.sum(Transaction.amount), Transaction.type)
            .where(
                Transaction.payment_method_id == pm.id,
                Transaction.bill_date < end_date,
                Transaction.deleted_at.is_(None),
                Transaction.platform_id.in_(allowed) if allowed is not None else True,
            )
            .group_by(Transaction.type)
        ).all()
        opening = float(pm.initial_balance or 0)
        for amount_sum, tx_type in before_row:
            if tx_type == "income":
                opening += float(amount_sum or 0)
            elif tx_type == "expense":
                opening -= float(amount_sum or 0)

        range_row = db.execute(
            select(func.sum(Transaction.amount), Transaction.type)
            .where(
                Transaction.payment_method_id == pm.id,
                Transaction.bill_date >= start_date,
                Transaction.bill_date <= end_date,
                Transaction.deleted_at.is_(None),
                Transaction.platform_id.in_(allowed) if allowed is not None else True,
            )
            .group_by(Transaction.type)
        ).all()
        recharge = 0.0
        payout = 0.0
        for amount_sum, tx_type in range_row:
            if tx_type == "income":
                recharge += float(amount_sum or 0)
            elif tx_type == "expense":
                payout += float(amount_sum or 0)
        closing = opening + recharge - payout
        total_opening += opening
        total_recharge += recharge
        total_payout += payout
        total_closing += closing
        ws_bal.append([pm.name, pm.channel_kind, opening, recharge, payout, closing])
    ws_bal.append(["总计", "-", total_opening, total_recharge, total_payout, total_closing])
    apply_money_format(ws_bal, [3, 4, 5, 6])

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    filename = f"report-{start_date}-to-{end_date}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/handover-excel")
def export_handover_excel(
    bill_date: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module("reports.query")),
):
    allowed = _scoped_platform_ids(db, current_user)
    tenant_id = get_current_tenant_id(db, current_user)
    if allowed == []:
        allowed = [-1]
    wb = Workbook()
    ws1 = wb.active
    ws1.title = "交班营业"
    ws1.append(["日期", "班次", "充值", "支出", "营业额"])
    shift_rows = db.execute(
        select(DailySummary.shift_id, func.sum(DailySummary.total_income), func.sum(DailySummary.total_expense), func.sum(DailySummary.net_profit))
        .where(DailySummary.bill_date == bill_date, DailySummary.platform_id.in_(allowed) if allowed is not None else True)
        .group_by(DailySummary.shift_id)
        .order_by(DailySummary.shift_id.asc())
    ).all()
    for r in shift_rows:
        ws1.append([bill_date, r[0], float(r[1] or 0), float(r[2] or 0), float(r[3] or 0)])
    apply_money_format(ws1, [3, 4, 5])

    ws2 = wb.create_sheet("支付方式余额")
    ws2.append(["支付方式", "期初余额", "充值", "支出", "期末余额"])
    methods_full = db.execute(_tenant_select(PaymentMethod, tenant_id).where(PaymentMethod.status == "enabled")).scalars().all()
    for pm in methods_full:
        before_row = db.execute(
            select(func.sum(Transaction.amount), Transaction.type)
            .where(Transaction.payment_method_id == pm.id, Transaction.bill_date < bill_date, Transaction.deleted_at.is_(None))
            .where(Transaction.platform_id.in_(allowed) if allowed is not None else True)
            .group_by(Transaction.type)
        ).all()
        opening = float(pm.initial_balance or 0)
        for amount_sum, tx_type in before_row:
            if tx_type == "income":
                opening += float(amount_sum or 0)
            elif tx_type == "expense":
                opening -= float(amount_sum or 0)
        day_row = db.execute(
            select(func.sum(Transaction.amount), Transaction.type)
            .where(Transaction.payment_method_id == pm.id, Transaction.bill_date == bill_date, Transaction.deleted_at.is_(None))
            .where(Transaction.platform_id.in_(allowed) if allowed is not None else True)
            .group_by(Transaction.type)
        ).all()
        recharge = 0.0
        payout = 0.0
        for amount_sum, tx_type in day_row:
            if tx_type == "income":
                recharge += float(amount_sum or 0)
            elif tx_type == "expense":
                payout += float(amount_sum or 0)
        ws2.append([pm.name, opening, recharge, payout, opening + recharge - payout])
    apply_money_format(ws2, [2, 3, 4, 5])

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    filename = f"handover-{bill_date}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/excel")
def export_excel(
    year: int,
    month: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_module("reports.monthly")),
):
    allowed = _scoped_platform_ids(db, current_user)
    if allowed == []:
        allowed = [-1]
    wb = Workbook()

    ws_tx = wb.active
    ws_tx.title = "流水明细"
    ws_tx.append(["日期", "班次", "平台", "类型", "项目", "金额", "备注", "业务组"])
    tx_rows = db.execute(
        select(Transaction).where(
            extract("year", Transaction.bill_date) == year,
            extract("month", Transaction.bill_date) == month,
            Transaction.deleted_at.is_(None),
            Transaction.platform_id.in_(allowed) if allowed is not None else True,
        )
    ).scalars().all()
    for tx in tx_rows:
        ws_tx.append(
            [
                tx.bill_date.isoformat(),
                tx.shift_id,
                tx.platform_id,
                tx.type,
                tx.category_id,
                float(tx.amount),
                tx.remark,
                tx.biz_group_no,
            ]
        )
    apply_money_format(ws_tx, [6])

    ws_daily = wb.create_sheet("每日汇总")
    ws_daily.append(["日期", "班次", "平台", "收入", "支出", "净盈利"])
    daily_rows = db.execute(
        select(DailySummary).where(
            extract("year", DailySummary.bill_date) == year,
            extract("month", DailySummary.bill_date) == month,
            DailySummary.platform_id.in_(allowed) if allowed is not None else True,
        )
    ).scalars().all()
    for row in daily_rows:
        ws_daily.append(
            [
                row.bill_date.isoformat(),
                row.shift_id,
                row.platform_id,
                float(row.total_income),
                float(row.total_expense),
                float(row.net_profit),
            ]
        )
    apply_money_format(ws_daily, [4, 5, 6])

    ws_bal = wb.create_sheet("账户余额")
    ws_bal.append(["日期", "班次", "账户", "理论余额", "实际余额", "差额"])
    bal_rows = db.execute(
        select(AccountSnapshot).where(
            extract("year", AccountSnapshot.bill_date) == year,
            extract("month", AccountSnapshot.bill_date) == month,
        )
    ).scalars().all()
    for row in bal_rows:
        ws_bal.append(
            [
                row.bill_date.isoformat(),
                row.shift_id,
                row.account_id,
                float(row.theoretical_balance),
                float(row.actual_balance) if row.actual_balance is not None else None,
                float(row.difference),
            ]
        )
    apply_money_format(ws_bal, [4, 5, 6])

    ws_month = wb.create_sheet("月度汇总")
    ws_month.append(["月份", "总收入", "总支出", "净盈利"])
    monthly_row = db.execute(
        select(func.sum(DailySummary.total_income), func.sum(DailySummary.total_expense), func.sum(DailySummary.net_profit)).where(
            extract("year", DailySummary.bill_date) == year,
            extract("month", DailySummary.bill_date) == month,
            DailySummary.platform_id.in_(allowed) if allowed is not None else True,
        )
    ).first()
    ws_month.append([f"{year:04d}-{month:02d}", float(monthly_row[0] or 0), float(monthly_row[1] or 0), float(monthly_row[2] or 0)])
    apply_money_format(ws_month, [2, 3, 4])

    ws_platform = wb.create_sheet("平台汇总")
    ws_platform.append(["平台ID", "收入", "支出", "净盈利"])
    agg_rows = db.execute(
        select(Transaction.platform_id, Transaction.type, Transaction.amount).where(
            extract("year", Transaction.bill_date) == year,
            extract("month", Transaction.bill_date) == month,
            Transaction.deleted_at.is_(None),
            Transaction.platform_id.in_(allowed) if allowed is not None else True,
        )
    ).all()
    plat_data: dict[int, dict[str, float]] = {}
    for platform_id, tx_type, amount in agg_rows:
        if platform_id not in plat_data:
            plat_data[platform_id] = {"income": 0.0, "expense": 0.0}
        if tx_type == "income":
            plat_data[platform_id]["income"] += float(amount or 0)
        elif tx_type == "expense":
            plat_data[platform_id]["expense"] += float(amount or 0)
    for pid, val in plat_data.items():
        ws_platform.append([pid, val["income"], val["expense"], val["income"] - val["expense"]])
    apply_money_format(ws_platform, [2, 3, 4])

    ws_project = wb.create_sheet("项目汇总")
    ws_project.append(["项目ID", "类型", "金额"])
    project_rows = db.execute(
        select(Transaction.category_id, Transaction.type, func.sum(Transaction.amount)).where(
            extract("year", Transaction.bill_date) == year,
            extract("month", Transaction.bill_date) == month,
            Transaction.deleted_at.is_(None),
            Transaction.platform_id.in_(allowed) if allowed is not None else True,
        ).group_by(Transaction.category_id, Transaction.type)
    ).all()
    for r in project_rows:
        ws_project.append([r[0], r[1], float(r[2] or 0)])
    apply_money_format(ws_project, [3])

    ws_logs = wb.create_sheet("修改记录")
    ws_logs.append(["用户ID", "模块", "动作", "修改前", "修改后", "时间"])
    logs = db.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(2000)).scalars().all()
    for log in logs:
        ws_logs.append([log.user_id, log.module, log.action, log.before_data, log.after_data, log.created_at.isoformat()])

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    filename = f"accounting-{year:04d}-{month:02d}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/super-tenant-summary-excel")
def export_super_tenant_summary_excel(
    start_date: str | None = None,
    end_date: str | None = None,
    tenant_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles({UserRole.SUPER_ADMIN.value, UserRole.PLATFORM_VIEWER.value})),
):
    wb = Workbook()
    ws = wb.active
    ws.title = "租户汇总"
    ws.append(["租户ID", "租户名称", "总收入", "总支出", "净利润"])

    stmt = (
        select(
            Tenant.id,
            Tenant.name,
            func.sum(DailySummary.total_income),
            func.sum(DailySummary.total_expense),
            func.sum(DailySummary.net_profit),
        )
        .select_from(Tenant)
        .join(TenantPlatformAccess, TenantPlatformAccess.tenant_id == Tenant.id)
        .join(DailySummary, DailySummary.platform_id == TenantPlatformAccess.platform_id)
    )
    if start_date:
        stmt = stmt.where(DailySummary.bill_date >= start_date)
    if end_date:
        stmt = stmt.where(DailySummary.bill_date <= end_date)
    if tenant_id:
        stmt = stmt.where(Tenant.id == tenant_id)
    rows = db.execute(stmt.group_by(Tenant.id, Tenant.name).order_by(Tenant.id.asc())).all()

    total_income = 0.0
    total_expense = 0.0
    total_net = 0.0
    for r in rows:
        income = float(r[2] or 0)
        expense = float(r[3] or 0)
        net = float(r[4] or 0)
        total_income += income
        total_expense += expense
        total_net += net
        ws.append([int(r[0]), r[1], income, expense, net])

    ws.append(["总计", "-", total_income, total_expense, total_net])
    apply_money_format(ws, [3, 4, 5])

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    filename = "super-tenant-summary.xlsx"
    db.add(
        AuditLog(
            user_id=current_user.id,
            module="exports",
            action="export_super_tenant_summary_excel",
            after_data=f"start_date={start_date},end_date={end_date},tenant_id={tenant_id}",
        )
    )
    db.commit()
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
