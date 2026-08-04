#!/bin/bash
# sync-dbs.sh — 从 multi-agent-sop-github 同步数据库到 OPC_ecommerce
# 用法：bash sync-dbs.sh

set -e

SOP_REPO="/c/Users/nicho/multi-agent-sop-github"
DB_DIR="/c/Users/nicho/OPC_ecommerce/shared/databases"

echo "=== 开始同步数据库 ==="
echo "源仓库: $SOP_REPO"
echo "目标目录: $DB_DIR"

# 检查源仓库是否存在
if [ ! -d "$SOP_REPO" ]; then
    echo "错误: 源仓库不存在: $SOP_REPO"
    exit 1
fi

# 检查目标目录是否存在
if [ ! -d "$DB_DIR" ]; then
    echo "创建目标目录: $DB_DIR"
    mkdir -p "$DB_DIR"
fi

# 切换到源仓库并拉取最新代码
cd "$SOP_REPO"
echo "拉取最新代码..."
git pull origin master 2>&1 || {
    echo "警告: git pull 失败，继续使用本地版本"
}

# 检查源数据库是否存在
if [ ! -f "$SOP_REPO/keyword_database.db" ]; then
    echo "错误: 源仓库缺少 keyword_database.db"
    exit 1
fi

if [ ! -f "$SOP_REPO/risk_keywords.db" ]; then
    echo "错误: 源仓库缺少 risk_keywords.db"
    exit 1
fi

# 同步数据库
echo "同步 keyword_database.db..."
cp "$SOP_REPO/keyword_database.db" "$DB_DIR/"

echo "同步 risk_keywords.db..."
cp "$SOP_REPO/risk_keywords.db" "$DB_DIR/"

# 验证同步结果
KEYWORD_COUNT=$(sqlite3 "$DB_DIR/keyword_database.db" "SELECT COUNT(*) FROM keywords;" 2>/dev/null || echo "0")
RISK_COUNT=$(sqlite3 "$DB_DIR/risk_keywords.db" "SELECT COUNT(*) FROM risk_keywords;" 2>/dev/null || echo "0")

echo ""
echo "=== 同步完成 ==="
echo "keyword_database.db: $KEYWORD_COUNT 条关键词"
echo "risk_keywords.db: $RISK_COUNT 条风险词"

# 记录同步时间
echo "$(date '+%Y-%m-%d %H:%M:%S') sync-dbs.sh completed" >> "$DB_DIR/sync.log"
