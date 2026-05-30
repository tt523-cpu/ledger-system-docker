"""
默认租户下线迁移脚本模板（手动执行前请先备份数据库）。

用途：
1) 将“默认租户”中的历史数据归档到指定历史租户（如“历史租户A”）
2) 确认所有非超管用户都已绑定到明确租户
3) 再移除系统中的自动默认租户初始化逻辑

说明：
- 该脚本仅为模板，不会自动执行任何写入。
- 正式执行前请根据生产数据规模补齐分批迁移与校验逻辑。
"""

from app.core.database import SessionLocal


def main():
    db = SessionLocal()
    try:
        # TODO: 1. 查找默认租户与目标历史租户
        # TODO: 2. 迁移 user_tenant_access / tenant_platform_access
        # TODO: 3. 校验所有普通用户都绑定了非默认租户
        # TODO: 4. 输出迁移统计并人工确认
        print("迁移模板已就绪，请按注释补齐后执行。")
    finally:
        db.close()


if __name__ == "__main__":
    main()
