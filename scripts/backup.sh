#!/usr/bin/env bash
# ============================================================
# netcheck-platform 数据备份（Linux/macOS）
# 备份 SQLite 数据库、巡检报告目录与日志目录到一个带时间戳的目录，
# 并清理超过保留天数的旧备份。
#
# 用法：
#   ./scripts/backup.sh                 # 使用默认路径
#   NETCHECK_DATA_DIR=... ./scripts/backup.sh
#
# 可覆盖的环境变量：
#   NETCHECK_DATA_DIR    数据库所在目录（默认 backend/data）
#   NETCHECK_REPORTS_DIR 报告目录（默认 backend/data/reports）
#   NETCHECK_BACKUPS_DIR 备份输出目录（默认 backups）
#   NETCHECK_KEEP_DAYS   保留天数（默认 30）
# ============================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${NETCHECK_DATA_DIR:-$ROOT/backend/data}"
REPORTS_DIR="${NETCHECK_REPORTS_DIR:-$DATA_DIR/reports}"
BACKUPS_DIR="${NETCHECK_BACKUPS_DIR:-$ROOT/backups}"
KEEP_DAYS="${NETCHECK_KEEP_DAYS:-30}"

DB_FILE="${DATA_DIR}/netcheck.db"
STAMP="$(date +%Y%m%d-%H%M%S)"
DEST="${BACKUPS_DIR}/${STAMP}"

mkdir -p "${DEST}"

if [ -f "${DB_FILE}" ]; then
  # SQLite WAL 日志一并复制，保证一致性
  cp "${DB_FILE}" "${DEST}/netcheck.db" 2>/dev/null || true
  [ -f "${DB_FILE}-wal" ] && cp "${DB_FILE}-wal" "${DEST}/netcheck.db-wal" || true
  [ -f "${DB_FILE}-shm" ] && cp "${DB_FILE}-shm" "${DEST}/netcheck.db-shm" || true
else
  echo "警告：未找到数据库文件 ${DB_FILE}，跳过数据库备份"
fi

if [ -d "${REPORTS_DIR}" ]; then
  cp -r "${REPORTS_DIR}" "${DEST}/reports"
else
  echo "警告：未找到报告目录 ${REPORTS_DIR}，跳过报告备份"
fi

# 压缩归档后删除临时目录
tar -czf "${DEST}.tar.gz" -C "${BACKUPS_DIR}" "${STAMP}" 2>/dev/null || true
rm -rf "${DEST}"

echo "备份完成：${DEST}.tar.gz"
echo "恢复方式：停止后端后，将归档解压，netcheck.db（及其 -wal/-shm）放回 ${DATA_DIR}，reports 放回 ${REPORTS_DIR}。"

# 清理过期备份
find "${BACKUPS_DIR}" -name '*.tar.gz' -mtime "+${KEEP_DAYS}" -delete 2>/dev/null || true
echo "已清理 ${KEEP_DAYS} 天前的旧备份。"