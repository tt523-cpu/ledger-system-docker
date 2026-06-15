import base64
import json
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError
from uuid import uuid4

from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_accessible_platform_ids, get_current_tenant_id, get_user_platform_ids, require_roles
from app.core.config import settings
from app.models.entities import AuditLog, Category, EntryType, EntryTypeSetting, ImportAlias, PaymentMethod, Platform, Transaction, User
from app.models.enums import TransactionType, UserRole
from app.schemas.common import BatchTransactionCreate, ImportAliasCreate, OffsetTransactionCreate, TransactionAIParseRequest, TransactionImportNormalizeRequest
from app.services.month_lock import assert_month_not_locked
from app.services.summary import rebuild_daily_summary_for_date


router = APIRouter(prefix="/transactions", tags=["transactions"])

ADMIN_UPDATABLE_FIELDS = {
    "type",
    "platform_id",
    "category_id",
    "account_id",
    "target_account_id",
    "payment_method_id",
    "amount",
    "remark",
    "biz_type_label",
}

BOOKKEEPER_UPDATABLE_FIELDS = {
    "category_id",
    "payment_method_id",
    "amount",
    "remark",
    "biz_type_label",
}


def normalize_tx_type(raw_type: str) -> str:
    if raw_type in {"redeem", "exchange", "兑奖", "mischarge", "误上"}:
        return TransactionType.EXPENSE.value
    if raw_type in {"reversal", "回冲", "调账"}:
        return TransactionType.ADJUST.value
    return raw_type


def default_type_label(raw_type: str, normalized: str) -> str:
    if raw_type in {"redeem", "exchange", "兑奖"}:
        return "兑奖"
    if raw_type in {"mischarge", "误上"}:
        return "误上"
    if raw_type in {"reversal", "回冲", "调账"}:
        return "回冲"
    if normalized == TransactionType.INCOME.value:
        return "充值"
    if normalized == TransactionType.EXPENSE.value:
        return "支出"
    if normalized == TransactionType.ADJUST.value:
        return "回冲"
    return raw_type


def type_requires_category(db: Session, tenant_id: int | None, type_label: str, normalized_type: str) -> bool:
    if normalized_type != TransactionType.EXPENSE.value:
        return False
    stmt = select(EntryType).where(EntryType.name == type_label)
    if tenant_id is not None:
        stmt = stmt.where(EntryType.tenant_id == tenant_id)
    et = db.execute(stmt).scalar_one_or_none()
    if et is None:
        return type_label == "支出"
    st = db.execute(select(EntryTypeSetting).where(EntryTypeSetting.entry_type_id == et.id)).scalar_one_or_none()
    if st is None:
        return type_label == "支出"
    return bool(st.requires_category)


def _tenant_rows(db: Session, model, tenant_id: int | None):
    stmt = select(model)
    if tenant_id is not None:
        stmt = stmt.where(model.tenant_id == tenant_id)
    return db.execute(stmt).scalars().all()


def _normalize_import_key(value: str | None) -> str:
    return "".join(str(value or "").strip().lower().split())


def _import_aliases(db: Session, tenant_id: int | None) -> dict[str, dict[str, int]]:
    stmt = select(ImportAlias)
    if tenant_id is not None:
        stmt = stmt.where(ImportAlias.tenant_id == tenant_id)
    rows = db.execute(stmt).scalars().all()
    aliases: dict[str, dict[str, int]] = {}
    for row in rows:
        aliases.setdefault(row.alias_type, {})[_normalize_import_key(row.alias_name)] = row.target_id
    return aliases


def _extract_json_object(text: str):
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            return json.loads(raw[start : end + 1])
        raise


def _call_deepseek(messages: list[dict], empty_detail: str = "DeepSeek返回内容为空") -> dict:
    if not settings.deepseek_api_key:
        raise HTTPException(status_code=400, detail="未配置 DEEPSEEK_API_KEY")

    api_base = settings.deepseek_api_base.rstrip("/")
    last_content = ""
    for attempt in range(2):
        payload = json.dumps(
            {
                "model": settings.deepseek_model,
                "messages": messages,
                "temperature": 0.1,
                "max_tokens": 4096,
                "reasoning_effort": "high",
                "thinking": {"type": "enabled"},
                "stream": False,
            }
        ).encode("utf-8")
        req = urlrequest.Request(
            f"{api_base}/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {settings.deepseek_api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlrequest.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise HTTPException(status_code=502, detail=f"DeepSeek调用失败: {detail or exc.reason}") from exc
        except URLError as exc:
            raise HTTPException(status_code=502, detail=f"DeepSeek连接失败: {exc.reason}") from exc
        except TimeoutError as exc:
            raise HTTPException(status_code=504, detail="DeepSeek调用超时") from exc

        content = data.get("choices", [{}])[0].get("message", {}).get("content") or ""
        last_content = content.strip()
        if last_content:
            try:
                return _extract_json_object(last_content)
            except Exception as exc:
                raise HTTPException(status_code=502, detail="DeepSeek返回内容不是有效JSON") from exc

        if attempt == 0:
            messages = [*messages, {"role": "user", "content": "上一次返回为空。请只返回一个JSON对象，格式为 {\"items\": []}，不要返回空内容。"}]

    raise HTTPException(status_code=502, detail=empty_detail)


def _call_qwen_vision(messages: list[dict], empty_detail: str = "千问视觉返回内容为空") -> dict:
    if not settings.qwen_api_key:
        raise HTTPException(status_code=400, detail="未配置 QWEN_API_KEY")

    api_base = settings.qwen_api_base.rstrip("/")
    payload = json.dumps(
        {
            "model": settings.qwen_vision_model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 4096,
            "stream": False,
            "enable_thinking": False,
        }
    ).encode("utf-8")
    req = urlrequest.Request(
        f"{api_base}/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {settings.qwen_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise HTTPException(status_code=502, detail=f"千问视觉调用失败: {detail or exc.reason}") from exc
    except URLError as exc:
        raise HTTPException(status_code=502, detail=f"千问视觉连接失败: {exc.reason}") from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="千问视觉调用超时") from exc

    content = data.get("choices", [{}])[0].get("message", {}).get("content") or ""
    content = content.strip()
    if not content:
        raise HTTPException(status_code=502, detail=empty_detail)
    try:
        parsed = _extract_json_object(content)
        if isinstance(parsed, dict):
            parsed.setdefault("_raw_content", content)
            return parsed
        return {"items": parsed, "_raw_content": content}
    except Exception as exc:
        raise HTTPException(status_code=502, detail="千问视觉返回内容不是有效JSON") from exc


def _ai_master_data(db: Session, tenant_id: int | None) -> tuple[dict, list[EntryType], list[Category], list[PaymentMethod], list[Platform]]:
    entry_types = _tenant_rows(db, EntryType, tenant_id)
    categories = _tenant_rows(db, Category, tenant_id)
    payment_methods = _tenant_rows(db, PaymentMethod, tenant_id)
    platforms = _tenant_rows(db, Platform, tenant_id)
    master_data = {
        "platforms": [
            {"name": x.name}
            for x in platforms
            if x.status == "enabled"
        ],
        "entry_types": [
            {"name": x.name, "effect": x.effect}
            for x in entry_types
            if x.status == "enabled"
        ],
        "expense_categories": [
            {"name": x.name}
            for x in categories
            if x.status == "enabled" and x.type == TransactionType.EXPENSE.value
        ],
        "payment_methods": [
            {"name": x.name, "channel_kind": x.channel_kind}
            for x in payment_methods
            if x.status == "enabled"
        ],
    }
    return master_data, entry_types, categories, payment_methods, platforms


def _build_import_messages(master_data: dict, user_content) -> list[dict]:
    messages = [
        {
            "role": "system",
            "content": (
                "你是记账流水导入助手。根据用户给出的文字或图片整理流水草稿，必须返回JSON对象。"
                "不要解释，不要Markdown。返回格式：{\"items\":[{\"platform_name\":字符串或null,\"type_label\":字符串,\"category_name\":字符串或null,"
                "\"amount\":数字,\"payment_method_name\":字符串或null,\"remark\":字符串}]}。"
                "platform_name根据图片或文字中的渠道/平台字段选择，必须尽量从platforms.name匹配，不要随意返回null；"
                "type_label只能从entry_types.name选择；category_name只能从expense_categories.name选择，无法确定则null；"
                "payment_method_name只能从payment_methods.name选择；如果来源有运营备注，优先把运营备注当账户名匹配到payment_method_name。"
                "金额必须大于0；remark保留财务备注、第三方订单号或其他关键备注。"
                "如果备注包含回充或回冲，type_label必须优先选择主数据中表示回冲/回充含义的类型，备注优先级高于交易类型。"
                "如果没有识别到流水，必须返回{\"items\":[]}，不能返回空字符串。"
            ),
        },
        {
            "role": "user",
            "content": user_content,
        },
    ]
    return messages


def _match_name(rows, raw_name: str | None):
    key = _normalize_import_key(raw_name)
    if not key:
        return None
    key_no_digits = "".join(ch for ch in key if not ch.isdigit())
    for row in rows:
        row_key = _normalize_import_key(row.name)
        if row_key == key:
            return row
    for row in rows:
        row_key = _normalize_import_key(row.name)
        if key in row_key or row_key in key:
            return row
    if key_no_digits and key_no_digits != key:
        for row in rows:
            row_key = _normalize_import_key(row.name)
            row_key_no_digits = "".join(ch for ch in row_key if not ch.isdigit())
            if key_no_digits == row_key_no_digits or key_no_digits in row_key_no_digits or row_key_no_digits in key_no_digits:
                return row
    for row in rows:
        row_key = _normalize_import_key(row.name)
        if len(key) == len(row_key) and len(key) >= 3:
            diff_count = sum(1 for left, right in zip(key, row_key) if left != right)
            if diff_count <= 1:
                return row
    return None


def _match_alias_or_name(rows, aliases: dict[str, dict[str, int]], alias_type: str, raw_name: str | None):
    key = _normalize_import_key(raw_name)
    alias_target_id = aliases.get(alias_type, {}).get(key)
    if alias_target_id is not None:
        for row in rows:
            if row.id == alias_target_id:
                return row
    return _match_name(rows, raw_name)


def _first_value(item: dict, names: list[str]):
    for name in names:
        value = item.get(name)
        if value not in (None, ""):
            return value
    return None


def _normalize_ai_items(parsed: dict, entry_types: list[EntryType], categories: list[Category], payment_methods: list[PaymentMethod], platforms: list[Platform], aliases: dict[str, dict[str, int]]) -> list[dict]:
    raw_items = parsed if isinstance(parsed, list) else parsed.get("items") if isinstance(parsed, dict) else None
    if not isinstance(raw_items, list):
        raise HTTPException(status_code=502, detail="AI返回缺少items")

    valid_entry_types = [x for x in entry_types if x.status == "enabled"]
    valid_categories = [x for x in categories if x.status == "enabled" and x.type == TransactionType.EXPENSE.value]
    valid_payment_methods = [x for x in payment_methods if x.status == "enabled"]
    valid_platforms = [x for x in platforms if x.status == "enabled"]
    reversal_entry_type = _match_alias_or_name(valid_entry_types, aliases, "entry_type", "回冲") or _match_alias_or_name(valid_entry_types, aliases, "entry_type", "回充")
    items = []
    for item in raw_items[:100]:
        if not isinstance(item, dict):
            continue
        try:
            amount = float(item.get("amount") or 0)
        except (TypeError, ValueError):
            amount = 0
        if amount <= 0:
            continue
        type_value = _first_value(item, ["type_label", "type", "transaction_type", "trade_type", "交易类型", "类型"])
        category_value = _first_value(item, ["category_name", "category", "项目", "分类"])
        payment_value = _first_value(item, ["payment_method_name", "payment_method", "account", "账户", "运营备注", "交易方式"])
        platform_value = _first_value(item, ["platform_name", "platform", "channel", "渠道", "平台"])
        remark_value = _first_value(item, ["remark", "财务备注", "备注", "原始行", "第三方订单号"])
        entry_type = _match_alias_or_name(valid_entry_types, aliases, "entry_type", type_value)
        type_label = entry_type.name if entry_type else None
        remark = str(remark_value or "").strip()
        if ("回充" in remark or "回冲" in remark) and reversal_entry_type:
            type_label = reversal_entry_type.name
        category = _match_alias_or_name(valid_categories, aliases, "category", category_value)
        payment_method = _match_alias_or_name(valid_payment_methods, aliases, "payment_method", payment_value)
        platform = _match_alias_or_name(valid_platforms, aliases, "platform", platform_value)
        items.append(
            {
                "platform_id": platform.id if platform else None,
                "platform_name": platform.name if platform else None,
                "raw_platform_name": str(platform_value or "").strip(),
                "type_label": type_label,
                "raw_type_label": str(type_value or "").strip(),
                "category_name": category.name if category else None,
                "raw_category_name": str(category_value or "").strip(),
                "amount": amount,
                "payment_method_name": payment_method.name if payment_method else None,
                "raw_payment_method_name": str(payment_value or "").strip(),
                "remark": remark,
            }
        )
    return items


@router.post("/import/ai-parse")
def ai_parse_transactions(
    payload: TransactionAIParseRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles({UserRole.ADMIN.value, UserRole.BOOKKEEPER.value})),
):
    tenant_id = get_current_tenant_id(db, current_user)
    master_data, entry_types, categories, payment_methods, platforms = _ai_master_data(db, tenant_id)
    aliases = _import_aliases(db, tenant_id)
    user_content = json.dumps(
        {
            "master_data": master_data,
            "text": payload.text,
        },
        ensure_ascii=False,
    )
    messages = _build_import_messages(master_data, user_content)
    parsed = _call_deepseek(messages)
    items = _normalize_ai_items(parsed, entry_types, categories, payment_methods, platforms, aliases)
    return {"items": items}


@router.post("/import/normalize")
def normalize_import_transactions(
    payload: TransactionImportNormalizeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles({UserRole.ADMIN.value, UserRole.BOOKKEEPER.value})),
):
    tenant_id = get_current_tenant_id(db, current_user)
    _, entry_types, categories, payment_methods, platforms = _ai_master_data(db, tenant_id)
    aliases = _import_aliases(db, tenant_id)
    items = _normalize_ai_items({"items": payload.items[:100]}, entry_types, categories, payment_methods, platforms, aliases)
    return {"items": items}


@router.post("/import/ai-parse-image")
async def ai_parse_transaction_image(
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles({UserRole.ADMIN.value, UserRole.BOOKKEEPER.value})),
):
    content_type = image.content_type or "application/octet-stream"
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="请上传图片文件")
    data = await image.read()
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="图片不能超过8MB")

    tenant_id = get_current_tenant_id(db, current_user)
    master_data, entry_types, categories, payment_methods, platforms = _ai_master_data(db, tenant_id)
    aliases = _import_aliases(db, tenant_id)
    image_url = f"data:{content_type};base64,{base64.b64encode(data).decode('ascii')}"
    prompt = (
        "请识别图片中的记账流水，忽略页面筛选条件、按钮、菜单等非流水内容。"
        "请只输出合法JSON对象，不要Markdown，不要解释。"
        "图片表格中的渠道列对应系统平台，必须逐行读取并输出到platform_name，不允许省略；实际金额列对应amount。"
        "交易类型默认决定type_label，运营备注优先级最高；如果运营备注包含回充或回冲，type_label必须选择master_data.entry_types中最接近回冲/回充含义的类型。"
        "运营备注列是账户名，必须优先输出到payment_method_name，并尽量匹配master_data.payment_methods.name。"
        "财务备注或第三方订单号输出到remark；没有财务备注时可用第三方订单号或其他关键字段作为remark。"
        "返回格式必须是：{\"items\":[{\"platform_name\":字符串或null,\"type_label\":字符串或null,\"category_name\":字符串或null,"
        "\"amount\":数字,\"payment_method_name\":字符串或null,\"remark\":字符串}]}。"
        "platform_name必须尽量从master_data.platforms.name中匹配，名称有数字后缀或OCR近似时选择最接近的平台；"
        "type_label只能从master_data.entry_types.name选择；category_name只能从master_data.expense_categories.name选择；"
        "payment_method_name只能从master_data.payment_methods.name选择；无法确定的字段用null；金额必须准确且大于0。"
        "如果没有识别到流水，返回{\"items\":[]}。master_data="
        + json.dumps(master_data, ensure_ascii=False)
    )
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": image_url}},
                {"type": "text", "text": prompt},
            ],
        }
    ]
    parsed = _call_qwen_vision(messages)
    items = _normalize_ai_items(parsed, entry_types, categories, payment_methods, platforms, aliases)
    return {"items": items, "raw": parsed.get("_raw_content") if isinstance(parsed, dict) else None}


@router.post("/import-aliases")
def create_import_alias(
    payload: ImportAliasCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles({UserRole.ADMIN.value, UserRole.BOOKKEEPER.value})),
):
    tenant_id = get_current_tenant_id(db, current_user)
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="current user not bound to tenant")
    alias_name = (payload.alias_name or "").strip()
    if not alias_name:
        raise HTTPException(status_code=400, detail="alias_name is required")

    target_model = {
        "platform": Platform,
        "entry_type": EntryType,
        "category": Category,
        "payment_method": PaymentMethod,
    }[payload.alias_type]
    target = db.execute(select(target_model).where(target_model.id == payload.target_id, target_model.tenant_id == tenant_id)).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="target not found")

    existing = db.execute(
        select(ImportAlias).where(
            ImportAlias.tenant_id == tenant_id,
            ImportAlias.alias_type == payload.alias_type,
            ImportAlias.alias_name == alias_name,
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.target_id = payload.target_id
        existing.created_by = current_user.id
        alias = existing
    else:
        alias = ImportAlias(
            tenant_id=tenant_id,
            alias_type=payload.alias_type,
            alias_name=alias_name,
            target_id=payload.target_id,
            created_by=current_user.id,
        )
        db.add(alias)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="alias already exists") from exc
    db.refresh(alias)
    return {"id": alias.id, "alias_type": alias.alias_type, "alias_name": alias.alias_name, "target_id": alias.target_id}


@router.post("/batch")
def create_batch_transactions(
    payload: BatchTransactionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles({UserRole.ADMIN.value, UserRole.BOOKKEEPER.value})),
): 
    tenant_id = get_current_tenant_id(db, current_user)
    if not payload.lines:
        raise HTTPException(status_code=400, detail="lines cannot be empty")
    try:
        assert_month_not_locked(db, payload.bill_date)
    except ValueError as exc:
        raise HTTPException(status_code=423, detail=str(exc)) from exc

    allowed_platform_ids = None
    if current_user.role == UserRole.BOOKKEEPER.value:
        platform_ids = get_accessible_platform_ids(db, current_user)
        allowed_platform_ids = set(platform_ids)
        if not allowed_platform_ids:
            raise HTTPException(status_code=400, detail="bookkeeper has no platform binding")
        if payload.platform_id is None:
            effective_platform_id = platform_ids[0]
        else:
            if payload.platform_id not in platform_ids:
                raise HTTPException(status_code=403, detail="no permission for selected platform")
            effective_platform_id = payload.platform_id
    else:
        if payload.platform_id is None:
            raise HTTPException(status_code=400, detail="platform_id is required")
        if current_user.role != UserRole.SUPER_ADMIN.value:
            allowed_platform_ids = set(get_accessible_platform_ids(db, current_user))
            if payload.platform_id not in allowed_platform_ids:
                raise HTTPException(status_code=403, detail="no permission for selected platform")
        effective_platform_id = payload.platform_id

    biz_group_no = uuid4().hex[:16]
    created = []

    for line in payload.lines:
        line_platform_id = line.platform_id or effective_platform_id
        if allowed_platform_ids is not None and line_platform_id not in allowed_platform_ids:
            raise HTTPException(status_code=403, detail="no permission for selected platform")
        normalized_type = normalize_tx_type(line.type)
        type_label = (line.type_label or "").strip() or default_type_label(line.type, normalized_type)

        if normalized_type == TransactionType.TRANSFER.value:
            raise HTTPException(status_code=400, detail="transfer is disabled")

        requires_category = type_requires_category(db, tenant_id, type_label, normalized_type)
        if requires_category and not line.category_id:
            raise HTTPException(status_code=400, detail="category_id is required for 支出")

        if line.category_id is not None:
            category_stmt = select(Category).where(Category.id == line.category_id)
            if tenant_id is not None:
                category_stmt = category_stmt.where(Category.tenant_id == tenant_id)
            category = db.execute(category_stmt).scalar_one_or_none()
            if category is None:
                raise HTTPException(status_code=404, detail=f"Category {line.category_id} not found")

        tx = Transaction(
            bill_date=payload.bill_date,
            shift_id=payload.shift_id,
            platform_id=line_platform_id,
            type=normalized_type,
            biz_type_label=type_label,
            category_id=line.category_id,
            account_id=line.account_id,
            target_account_id=line.target_account_id,
            payment_method_id=line.payment_method_id,
            amount=line.amount,
            remark=line.remark,
            biz_group_no=biz_group_no,
            operator_id=current_user.id,
        )
        db.add(tx)
        created.append(tx)

    db.flush()
    rebuild_daily_summary_for_date(db, payload.bill_date)

    db.add(
        AuditLog(
            user_id=current_user.id,
            module="transactions",
            action="create_batch",
            before_data=None,
            after_data=f"count={len(created)},group={biz_group_no}",
        )
    )

    db.commit()
    return {"created_count": len(created), "biz_group_no": biz_group_no}


@router.get("")
def list_transactions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    bill_date: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    shift_id: int | None = None,
    platform_id: int | None = None,
    tx_type: str | None = None,
    category_id: int | None = None,
    keyword: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles({UserRole.ADMIN.value, UserRole.BOOKKEEPER.value, UserRole.VIEWER.value})),
):
    tenant_id = get_current_tenant_id(db, current_user)
    stmt = select(Transaction).where(Transaction.deleted_at.is_(None))
    count_stmt = select(func.count(Transaction.id)).where(Transaction.deleted_at.is_(None))
    summary_stmt = select(
        func.sum(case((Transaction.type == "expense", Transaction.amount), else_=0)),
        func.sum(case((Transaction.biz_type_label == "充值", Transaction.amount), else_=0)),
        func.sum(case((Transaction.biz_type_label == "兑奖", Transaction.amount), else_=0)),
    ).where(Transaction.deleted_at.is_(None))
    expense_detail_stmt = select(
        Transaction.category_id,
        Transaction.biz_type_label,
        func.sum(Transaction.amount),
    ).where(Transaction.deleted_at.is_(None), Transaction.type == "expense")
    if bill_date:
        stmt = stmt.where(Transaction.bill_date == bill_date)
        count_stmt = count_stmt.where(Transaction.bill_date == bill_date)
        summary_stmt = summary_stmt.where(Transaction.bill_date == bill_date)
        expense_detail_stmt = expense_detail_stmt.where(Transaction.bill_date == bill_date)
    else:
        if start_date:
            stmt = stmt.where(Transaction.bill_date >= start_date)
            count_stmt = count_stmt.where(Transaction.bill_date >= start_date)
            summary_stmt = summary_stmt.where(Transaction.bill_date >= start_date)
            expense_detail_stmt = expense_detail_stmt.where(Transaction.bill_date >= start_date)
        if end_date:
            stmt = stmt.where(Transaction.bill_date <= end_date)
            count_stmt = count_stmt.where(Transaction.bill_date <= end_date)
            summary_stmt = summary_stmt.where(Transaction.bill_date <= end_date)
            expense_detail_stmt = expense_detail_stmt.where(Transaction.bill_date <= end_date)
    if shift_id:
        stmt = stmt.where(Transaction.shift_id == shift_id)
        count_stmt = count_stmt.where(Transaction.shift_id == shift_id)
        summary_stmt = summary_stmt.where(Transaction.shift_id == shift_id)
        expense_detail_stmt = expense_detail_stmt.where(Transaction.shift_id == shift_id)
    if platform_id:
        stmt = stmt.where(Transaction.platform_id == platform_id)
        count_stmt = count_stmt.where(Transaction.platform_id == platform_id)
        summary_stmt = summary_stmt.where(Transaction.platform_id == platform_id)
        expense_detail_stmt = expense_detail_stmt.where(Transaction.platform_id == platform_id)
    if current_user.role in {UserRole.ADMIN.value, UserRole.BOOKKEEPER.value, UserRole.VIEWER.value}:
        platform_ids = get_accessible_platform_ids(db, current_user)
        if platform_ids:
            stmt = stmt.where(Transaction.platform_id.in_(platform_ids))
            count_stmt = count_stmt.where(Transaction.platform_id.in_(platform_ids))
            summary_stmt = summary_stmt.where(Transaction.platform_id.in_(platform_ids))
            expense_detail_stmt = expense_detail_stmt.where(Transaction.platform_id.in_(platform_ids))
        elif current_user.role != UserRole.SUPER_ADMIN.value:
            return {
                "items": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
                "summary": {"expense": 0, "recharge": 0, "redeem": 0},
            }
    if tx_type:
        stmt = stmt.where(Transaction.type == tx_type)
        count_stmt = count_stmt.where(Transaction.type == tx_type)
        summary_stmt = summary_stmt.where(Transaction.type == tx_type)
        expense_detail_stmt = expense_detail_stmt.where(Transaction.type == tx_type)
    if category_id:
        stmt = stmt.where(Transaction.category_id == category_id)
        count_stmt = count_stmt.where(Transaction.category_id == category_id)
        summary_stmt = summary_stmt.where(Transaction.category_id == category_id)
        expense_detail_stmt = expense_detail_stmt.where(Transaction.category_id == category_id)
    if keyword:
        stmt = stmt.where(Transaction.remark.like(f"%{keyword}%"))
        count_stmt = count_stmt.where(Transaction.remark.like(f"%{keyword}%"))
        summary_stmt = summary_stmt.where(Transaction.remark.like(f"%{keyword}%"))
        expense_detail_stmt = expense_detail_stmt.where(Transaction.remark.like(f"%{keyword}%"))

    total = db.execute(count_stmt).scalar_one()
    rows = db.execute(
        stmt.order_by(Transaction.id.desc()).offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    platform_ids_in_rows = sorted({int(r.platform_id) for r in rows if r.platform_id is not None})
    payment_method_ids_in_rows = sorted({int(r.payment_method_id) for r in rows if r.payment_method_id is not None})

    platform_name_map: dict[int, str] = {}
    payment_method_name_map: dict[int, str] = {}
    if platform_ids_in_rows:
        platform_stmt = select(Platform.id, Platform.name).where(Platform.id.in_(platform_ids_in_rows))
        if tenant_id is not None:
            platform_stmt = platform_stmt.where(Platform.tenant_id == tenant_id)
        platform_name_map = {int(pid): name for pid, name in db.execute(platform_stmt).all()}
    if payment_method_ids_in_rows:
        payment_stmt = select(PaymentMethod.id, PaymentMethod.name).where(PaymentMethod.id.in_(payment_method_ids_in_rows))
        if tenant_id is not None:
            payment_stmt = payment_stmt.where(PaymentMethod.tenant_id == tenant_id)
        payment_method_name_map = {int(pid): name for pid, name in db.execute(payment_stmt).all()}

    summary_row = db.execute(summary_stmt).first()
    expense_rows = db.execute(expense_detail_stmt.group_by(Transaction.category_id, Transaction.biz_type_label)).all()
    category_stmt = select(Category)
    if tenant_id is not None:
        category_stmt = category_stmt.where(Category.tenant_id == tenant_id)
    category_map = {c.id: c.name for c in db.execute(category_stmt).scalars().all()}
    expense_detail = "，".join(
        f"{(category_map.get(r[0], f'项目#{r[0]}') if r[0] is not None else ((r[1] or '-').strip() or '-'))}:{float(r[2] or 0):.2f}"
        for r in expense_rows
    )
    return {
        "items": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
        "platform_name_map": platform_name_map,
        "payment_method_name_map": payment_method_name_map,
        "summary": {
            "expense": float(summary_row[0] or 0),
            "recharge": float(summary_row[1] or 0),
            "redeem": float(summary_row[2] or 0),
            "expense_detail": expense_detail,
        },
    }


@router.put("/{tx_id}")
def update_transaction(
    tx_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles({UserRole.ADMIN.value, UserRole.BOOKKEEPER.value})),
):
    tx = db.get(Transaction, tx_id)
    if tx is None or tx.deleted_at is not None:
        raise HTTPException(status_code=404, detail="transaction not found")

    if current_user.role == UserRole.BOOKKEEPER.value:
        platform_ids = get_accessible_platform_ids(db, current_user)
        if tx.platform_id not in platform_ids:
            raise HTTPException(status_code=403, detail="bookkeeper can only edit own platform transactions")
    elif current_user.role != UserRole.SUPER_ADMIN.value:
        allowed = set(get_accessible_platform_ids(db, current_user))
        if tx.platform_id not in allowed:
            raise HTTPException(status_code=403, detail="no permission for this transaction")

    old_bill_date = tx.bill_date
    old_shift_id = tx.shift_id
    old_platform_id = tx.platform_id

    before = {
        "amount": str(tx.amount),
        "type": tx.type,
        "category_id": tx.category_id,
        "remark": tx.remark,
        "biz_type_label": tx.biz_type_label,
    }
    updatable = ADMIN_UPDATABLE_FIELDS if current_user.role == UserRole.ADMIN.value else BOOKKEEPER_UPDATABLE_FIELDS

    blocked_changed = []
    for k, v in payload.items():
        if k in updatable:
            continue
        existing_val = getattr(tx, k, None)
        cmp_val = v
        if k == "type":
            cmp_val = normalize_tx_type(v)
        if existing_val != cmp_val:
            blocked_changed.append(k)
    if blocked_changed:
        raise HTTPException(status_code=403, detail=f"no permission to edit fields: {', '.join(blocked_changed)}")

    for k, v in payload.items():
        if k in updatable:
            if k == "type":
                v = normalize_tx_type(v)
            setattr(tx, k, v)

    label_for_check = tx.biz_type_label or default_type_label(tx.type, tx.type)
    tenant_id = get_current_tenant_id(db, current_user)
    requires_category = type_requires_category(db, tenant_id, label_for_check, tx.type)
    if requires_category and not tx.category_id:
        raise HTTPException(status_code=400, detail="category_id is required for 支出")
    if not requires_category:
        tx.category_id = None

    db.flush()
    rebuild_daily_summary_for_date(db, tx.bill_date)
    if old_bill_date != tx.bill_date:
        rebuild_daily_summary_for_date(db, old_bill_date)
    db.add(
        AuditLog(
            user_id=current_user.id,
            module="transactions",
            action="update",
            before_data=str(before),
            after_data=str(payload),
        )
    )
    db.commit()
    return {"ok": True}


@router.delete("/{tx_id}")
def soft_delete_transaction(
    tx_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles({UserRole.ADMIN.value, UserRole.BOOKKEEPER.value})),
):
    tx = db.get(Transaction, tx_id)
    if tx is None or tx.deleted_at is not None:
        raise HTTPException(status_code=404, detail="transaction not found")

    if current_user.role == UserRole.BOOKKEEPER.value:
        platform_ids = get_accessible_platform_ids(db, current_user)
        if tx.platform_id not in platform_ids:
            raise HTTPException(status_code=403, detail="bookkeeper can only delete own platform transactions")
    elif current_user.role != UserRole.SUPER_ADMIN.value:
        allowed = set(get_accessible_platform_ids(db, current_user))
        if tx.platform_id not in allowed:
            raise HTTPException(status_code=403, detail="no permission for this transaction")
    try:
        assert_month_not_locked(db, tx.bill_date)
    except ValueError as exc:
        raise HTTPException(status_code=423, detail=str(exc)) from exc

    tx.deleted_at = datetime.utcnow()
    db.flush()
    rebuild_daily_summary_for_date(db, tx.bill_date)
    db.add(
        AuditLog(
            user_id=current_user.id,
            module="transactions",
            action="delete",
            before_data=f"id={tx.id}",
            after_data=None,
        )
    )
    db.commit()
    return {"ok": True}


@router.post("/offset")
def create_offset_transactions(
    payload: OffsetTransactionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles({UserRole.ADMIN.value, UserRole.BOOKKEEPER.value})),
):
    if current_user.role == UserRole.BOOKKEEPER.value:
        platform_ids = get_accessible_platform_ids(db, current_user)
        if not platform_ids:
            raise HTTPException(status_code=400, detail="bookkeeper has no platform binding")
        if payload.platform_id is None:
            effective_platform_id = platform_ids[0]
        else:
            if payload.platform_id not in platform_ids:
                raise HTTPException(status_code=403, detail="no permission for selected platform")
            effective_platform_id = payload.platform_id
    else:
        if payload.platform_id is None:
            raise HTTPException(status_code=400, detail="platform_id is required")
        if current_user.role != UserRole.SUPER_ADMIN.value:
            allowed = set(get_accessible_platform_ids(db, current_user))
            if payload.platform_id not in allowed:
                raise HTTPException(status_code=403, detail="no permission for selected platform")
        effective_platform_id = payload.platform_id
    try:
        assert_month_not_locked(db, payload.bill_date)
    except ValueError as exc:
        raise HTTPException(status_code=423, detail=str(exc)) from exc

    biz_group_no = uuid4().hex[:16]

    recharge = Transaction(
        bill_date=payload.bill_date,
        shift_id=payload.shift_id,
        platform_id=effective_platform_id,
        type=TransactionType.INCOME.value,
        category_id=payload.recharge_category_id,
        payment_method_id=payload.payment_method_id,
        amount=payload.amount,
        remark=f"[offset-in] {payload.remark}",
        biz_group_no=biz_group_no,
        operator_id=current_user.id,
    )
    payout = Transaction(
        bill_date=payload.bill_date,
        shift_id=payload.shift_id,
        platform_id=effective_platform_id,
        type=TransactionType.EXPENSE.value,
        category_id=payload.payout_category_id,
        payment_method_id=payload.payment_method_id,
        amount=payload.amount,
        people_count=None,
        remark=f"[offset-out] {payload.remark}",
        biz_group_no=biz_group_no,
        operator_id=current_user.id,
    )
    db.add(recharge)
    db.add(payout)

    db.flush()
    rebuild_daily_summary_for_date(db, payload.bill_date)
    db.add(
        AuditLog(
            user_id=current_user.id,
            module="transactions",
            action="create_offset",
            before_data=None,
            after_data=f"amount={payload.amount},group={biz_group_no}",
        )
    )
    db.commit()
    return {"created_count": 2, "biz_group_no": biz_group_no}
    try:
        assert_month_not_locked(db, tx.bill_date)
    except ValueError as exc:
        raise HTTPException(status_code=423, detail=str(exc)) from exc
