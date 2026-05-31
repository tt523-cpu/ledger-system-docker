#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/www/wwwroot/ledger-system"
REPO_URL="https://github.com/tt523-cpu/ledger-system-docker.git"

echo "=============================="
echo "1. 安装基础工具"
echo "=============================="

apt-get update
apt-get install -y ca-certificates curl gnupg git openssl lsb-release

echo "=============================="
echo "2. 检查 / 安装 Docker"
echo "=============================="

if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  . /etc/os-release
  install -m 0755 -d /etc/apt/keyrings

  if [ "$ID" = "ubuntu" ]; then
    DOCKER_OS="ubuntu"
    DOCKER_CODENAME="${UBUNTU_CODENAME:-$VERSION_CODENAME}"
  elif [ "$ID" = "debian" ]; then
    DOCKER_OS="debian"
    DOCKER_CODENAME="$VERSION_CODENAME"
  else
    echo "当前系统不是 Ubuntu/Debian，尝试安装系统自带 Docker..."
    apt-get install -y docker.io docker-compose-plugin
    systemctl enable docker
    systemctl restart docker
    docker --version
    docker compose version
    exit 0
  fi

  rm -f /etc/apt/keyrings/docker.asc
  curl -fsSL "https://download.docker.com/linux/${DOCKER_OS}/gpg" -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc

  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/${DOCKER_OS} ${DOCKER_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list

  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

systemctl enable docker
systemctl restart docker

echo "Docker 版本："
docker --version
docker compose version

echo "=============================="
echo "3. 拉取项目代码"
echo "=============================="

mkdir -p /www/wwwroot

if [ -d "$PROJECT_DIR" ]; then
  BACKUP_DIR="${PROJECT_DIR}.bak.$(date +%Y%m%d_%H%M%S)"
  echo "检测到旧目录，备份到：$BACKUP_DIR"
  mv "$PROJECT_DIR" "$BACKUP_DIR"
fi

git clone "$REPO_URL" "$PROJECT_DIR"
cd "$PROJECT_DIR"

echo "=============================="
echo "4. 写入生产环境配置"
echo "=============================="

cat > .env.prod <<EOF
SECRET_KEY=$(openssl rand -hex 32)
ACCESS_TOKEN_EXPIRE_MINUTES=1440
MYSQL_USER=ledger
MYSQL_PASSWORD=baidu.com123
MYSQL_DB=accounting
EOF

echo "=============================="
echo "5. 固定端口为 127.0.0.1:5173:80"
echo "=============================="

sed -i 's#- "80:80"#- "127.0.0.1:5173:80"#g' docker-compose.yml || true
sed -i "s#- '80:80'#- '127.0.0.1:5173:80'#g" docker-compose.yml || true
sed -i 's#"80:80"#"127.0.0.1:5173:80"#g' docker-compose.yml || true
sed -i "s#'80:80'#'127.0.0.1:5173:80'#g" docker-compose.yml || true

echo "当前端口配置："
grep -n "5173:80\|80:80" docker-compose.yml || true

echo "=============================="
echo "6. 构建并启动"
echo "=============================="

docker compose --env-file .env.prod up -d --build

echo "=============================="
echo "7. 等待数据库和后端启动"
echo "=============================="

sleep 20

echo "=============================="
echo "8. 执行数据库迁移"
echo "=============================="

docker compose --env-file .env.prod exec -T backend sh -lc 'cd /app && alembic -c alembic.ini upgrade head' || true

echo "=============================="
echo "9. 重置管理员账号"
echo "=============================="

docker compose --env-file .env.prod exec -T backend python - <<'PY'
from sqlalchemy import select
from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.entities import User
from app.models.enums import GenericStatus, UserRole

db = SessionLocal()

try:
    user = db.execute(select(User).where(User.username == "admin")).scalar_one_or_none()

    if user is None:
        user = User(
            username="admin",
            password_hash=get_password_hash("admin123456"),
            role=UserRole.SUPER_ADMIN.value,
            status=GenericStatus.ENABLED.value,
        )
        db.add(user)
    else:
        user.password_hash = get_password_hash("admin123456")
        user.role = UserRole.SUPER_ADMIN.value
        user.status = GenericStatus.ENABLED.value

    db.commit()
    print("管理员账号已设置：admin / admin123456")
finally:
    db.close()
PY

echo "=============================="
echo "10. 查看容器状态"
echo "=============================="

docker compose --env-file .env.prod ps

echo "=============================="
echo "部署完成"
echo "=============================="
echo "宝塔反代目标：http://127.0.0.1:5173"
echo "登录账号：admin"
echo "登录密码：admin123456"
echo "提示：如后续执行了“恢复备份(JSON)”，users 会被覆盖；可再次运行第 9 步重置密码。"
