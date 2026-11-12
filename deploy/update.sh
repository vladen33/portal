#!/usr/bin/env bash
#
# Обновление портала до новой версии кода.
#
# Запускать от root из каталога НОВОЙ версии (например, клона тега):
#   sudo /opt/portal-release/deploy/update.sh
#
# Порядок действий:
#   1) резервная копия БД и .env;
#   2) остановка службы portal;
#   3) копирование кода в каталог установки (rsync --delete);
#   4) зависимости, миграции, статика, проверка настроек;
#   5) запуск службы и проверка /healthz/.
#
# При ошибке скрипт запускает службу обратно и напоминает,
# где лежит бэкап. Обратные миграции не выполняются.
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

APP_DIR="${APP_DIR:-/srv/portal}"
APP_USER="${APP_USER:-portal}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/portal}"
HEALTH_URL="${HEALTH_URL:-}"

log() {
    printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"
}

die() {
    printf '[%s] ОШИБКА: %s\n' "$(date +%H:%M:%S)" "$*" >&2
    exit 1
}

[ "$(id -u)" -eq 0 ] || die "запускать нужно от root"
[ -d "$APP_DIR" ] || die "не найден каталог установки ${APP_DIR}"
if [ "$SOURCE_DIR" = "$APP_DIR" ]; then
    die "запускайте скрипт из каталога новой версии, а не из ${APP_DIR}"
fi

# Выполняет команду в каталоге приложения от имени пользователя портала.
run_as_app() {
    runuser -u "$APP_USER" -- env "HOME=/var/lib/${APP_USER}" \
        bash -c 'cd "$1" && shift && exec "$@"' _ "$APP_DIR" "$@"
}

# Запускает службу обратно, если обновление упало.
restore_on_error() {
    local code=$?
    trap - ERR
    printf '[%s] ОБНОВЛЕНИЕ ПРЕРВАНО (код %s)\n' \
        "$(date +%H:%M:%S)" "$code" >&2
    printf 'Код в %s мог остаться в промежуточном состоянии.\n' \
        "$APP_DIR" >&2
    printf 'Бэкап: %s (порядок восстановления — docs/RESTORE.md).\n' \
        "$BACKUP_DIR" >&2
    systemctl start portal || true
    exit "$code"
}

log "бэкап перед обновлением"
APP_DIR="$APP_DIR" BACKUP_DIR="$BACKUP_DIR" \
    "${APP_DIR}/deploy/backup.sh"

trap restore_on_error ERR

log "остановка службы portal"
systemctl stop portal

log "копирование кода: ${SOURCE_DIR} -> ${APP_DIR}"
rsync -a --delete \
    --exclude venv/ \
    --exclude .venv/ \
    --exclude .env \
    --exclude .git/ \
    --exclude staticfiles/ \
    --exclude media/ \
    --exclude db.sqlite3 \
    --exclude __pycache__/ \
    --exclude .pytest_cache/ \
    --exclude .ruff_cache/ \
    --exclude logs/ \
    "${SOURCE_DIR}/" "${APP_DIR}/"
chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"

log "установка зависимостей"
run_as_app venv/bin/python -m pip install -r requirements.txt

log "миграции"
run_as_app venv/bin/python manage.py migrate --noinput

log "сборка статики"
run_as_app venv/bin/python manage.py collectstatic --noinput
# nginx работает от www-data и должен читать собранную статику.
chmod -R o+rX "${APP_DIR}/staticfiles"

log "проверка настроек"
run_as_app venv/bin/python manage.py check --deploy --fail-level=ERROR

log "запуск службы portal"
systemctl start portal
for _ in $(seq 1 30); do
    systemctl is-active --quiet portal && break
    sleep 1
done
systemctl is-active --quiet portal \
    || die "служба portal не запустилась: journalctl -u portal -n 50"

if [ -n "$HEALTH_URL" ]; then
    log "проверка живости ${HEALTH_URL}"
    for _ in $(seq 1 10); do
        if curl -fsSk --max-time 5 "$HEALTH_URL" >/dev/null; then
            log "портал отвечает"
            trap - ERR
            exit 0
        fi
        sleep 2
    done
    die "портал не отвечает по ${HEALTH_URL}"
fi

trap - ERR
log "обновление завершено"
