#!/usr/bin/env bash
#
# Резервная копия портала: база MS SQL Server и файлы из MEDIA_ROOT.
#
# Пример запуска из cron (каждый день в 2:30):
#   30 2 * * * /srv/portal/deploy/backup.sh \
#       >> /var/log/portal-backup.log 2>&1
#
# Переменные DB_* берутся из .env проекта. BACKUP_DIR, RETENTION_DAYS
# и MSSQL_CONTAINER можно переопределить в окружении cron.
set -euo pipefail

APP_DIR="${APP_DIR:-/srv/portal}"
ENV_FILE="${APP_DIR}/.env"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/portal}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
MSSQL_CONTAINER="${MSSQL_CONTAINER:-portal-mssql}"

read_env() {
    # Читает значение из .env без исполнения файла: секреты могут
    # содержать символы, опасные для bash ($, (, ), !, %).
    grep -E "^$1=" "${ENV_FILE}" 2>/dev/null \
        | tail -n 1 \
        | cut -d= -f2- \
        | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//"
}

DB_NAME="${DB_NAME:-$(read_env DB_NAME)}"
DB_USER="${DB_USER:-$(read_env DB_USER)}"
DB_PASSWORD="${DB_PASSWORD:-$(read_env DB_PASSWORD)}"
MEDIA_DIR="${DJANGO_MEDIA_ROOT:-$(read_env DJANGO_MEDIA_ROOT)}"
MEDIA_DIR="${MEDIA_DIR:-${APP_DIR}/media}"

: "${DB_NAME:?DB_NAME не задан в .env}"
: "${DB_USER:?DB_USER не задан в .env}"
: "${DB_PASSWORD:?DB_PASSWORD не задан в .env}"

# --- Проверка режима -------------------------------------------------------
# Дамп делает контейнер MSSQL. Во внешнем режиме копию настраивают
# на стороне сервера БД, здесь поддерживать её нельзя.
DB_MODE="$(read_env DEPLOY_DB_MODE)"
if [ "${DB_MODE}" = "external" ]; then
    echo "Режим external: бэкап MSSQL настраивается на сервере БД." >&2
    exit 1
fi
if ! command -v docker >/dev/null 2>&1; then
    echo "Не найден docker: бэкап контейнера MSSQL невозможен." >&2
    exit 1
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
mkdir -p "${BACKUP_DIR}"

# --- База данных ----------------------------------------------------------
DB_FILE="/var/opt/mssql/backup/${DB_NAME}-${STAMP}.bak"
docker exec "${MSSQL_CONTAINER}" mkdir -p /var/opt/mssql/backup
SQLCMD="/opt/mssql-tools18/bin/sqlcmd"
if ! docker exec "${MSSQL_CONTAINER}" test -x "${SQLCMD}"; then
    echo "В контейнере ${MSSQL_CONTAINER} нет ${SQLCMD}." >&2
    exit 1
fi
# Пароль передаём переменной окружения SQLCMDPASSWORD: он не виден
# в списке процессов хоста и не попадает в лог cron.
SQLCMDPASSWORD="${DB_PASSWORD}" docker exec -i \
    -e SQLCMDPASSWORD "${MSSQL_CONTAINER}" \
    "${SQLCMD}" \
    -S localhost -U "${DB_USER}" -C \
    -Q "BACKUP DATABASE [${DB_NAME}] TO DISK = N'${DB_FILE}' WITH INIT, CHECKSUM"
docker cp "${MSSQL_CONTAINER}:${DB_FILE}" \
    "${BACKUP_DIR}/${DB_NAME}-${STAMP}.bak"
docker exec "${MSSQL_CONTAINER}" rm -f "${DB_FILE}"

# --- Настройки приложения --------------------------------------------------
# Без копии .env восстановление неполное: нужны SECRET_KEY и параметры БД.
if [ -f "${ENV_FILE}" ]; then
    cp -a "${ENV_FILE}" "${BACKUP_DIR}/env-${STAMP}.bak"
    chmod 600 "${BACKUP_DIR}/env-${STAMP}.bak"
fi

# --- Файлы MEDIA_ROOT ------------------------------------------------------
if [ -d "${MEDIA_DIR}" ]; then
    tar -C "$(dirname "${MEDIA_DIR}")" \
        -czf "${BACKUP_DIR}/media-${STAMP}.tar.gz" \
        "$(basename "${MEDIA_DIR}")"
else
    echo "Каталог ${MEDIA_DIR} отсутствует, файлы не архивируются."
fi

# --- Ротация --------------------------------------------------------------
find "${BACKUP_DIR}" -type f -mtime "+${RETENTION_DAYS}" -delete
chmod 600 "${BACKUP_DIR}"/* 2>/dev/null || true

echo "Готово: ${BACKUP_DIR} (${STAMP})"
