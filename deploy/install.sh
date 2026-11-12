#!/usr/bin/env bash
#
# Установщик портала на Ubuntu/Debian.
#
# Примеры:
#   sudo deploy/install.sh --db=docker --domain=portal.example.local
#   sudo deploy/install.sh --db=external --db-host=10.0.0.5 \
#       --db-user=portal --create-db
#   deploy/install.sh --check --db=docker
#   deploy/install.sh --dry-run --db=external
#
# Полная справка: deploy/install.sh --help

# Часть переменных используется подключаемыми модулями deploy/install/*.sh.
# shellcheck disable=SC2034,SC2153

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
LIB_DIR="${SCRIPT_DIR}/install"
# Шаблоны берутся из каталога скрипта, а не из каталога установки:
# так dry-run работает до копирования кода.
DEPLOY_DIR="$SCRIPT_DIR"

# --- Значения по умолчанию -------------------------------------------------
APP_DIR="/srv/portal"
APP_USER="portal"
DOMAIN="portal.example.local"

TLS_MODE="selfsigned"    # selfsigned | existing | none
TLS_CERT=""
TLS_KEY=""
TLS_DAYS=825

DB_MODE=""               # docker | external
DB_HOST="127.0.0.1"
DB_PORT="1433"
DB_NAME="portal"
DB_USER="sa"
DB_PASSWORD=""
SA_PASSWORD=""
MSSQL_HOST_PORT="1433"
DB_TRUST_CERT=""         # пусто — вычислить по режиму
CREATE_DB=0

ADMIN_USER="admin"
ADMIN_EMAIL="admin@example.local"
ADMIN_PASSWORD=""
NO_ADMIN=0

BACKUP_DIR="/var/backups/portal"
BACKUP_SCHEDULE="30 2 * * *"
BACKUP_RETENTION=30
NO_BACKUP_CRON=0

LOG_DIR="/var/log/portal"
SKIP_FIREWALL=0
FORCE_ENV=0
YES=0
CHECK_ONLY=0
DRY_RUN=0
ALLOW_HTTP=0
LOG_FILE="/dev/null"

VALUE_OPTS=" --db --app-dir --app-user --domain --tls --cert --key \
--tls-days --db-host --db-port --db-name --db-user --db-password \
--sa-password --mssql-host-port --admin-user --admin-email \
--admin-password --backup-dir --backup-schedule --backup-retention "

usage() {
    cat <<'EOF'
Установщик портала (Ubuntu/Debian).

Режимы базы:
  --db=docker            MS SQL Server в контейнере на этом сервере
  --db=external          подключение к MSSQL в локальной сети

Основные параметры:
  --app-dir=DIR          каталог установки (/srv/portal)
  --app-user=USER        системный пользователь (portal)
  --domain=NAME          доменное имя портала

TLS:
  --tls=selfsigned|existing|none   (по умолчанию selfsigned)
  --cert=FILE --key=FILE           для --tls=existing
  --tls-days=DAYS                  срок самоподписанного (825)
  --allow-http                     разрешить режим без TLS

MS SQL Server:
  --db-host=HOST --db-port=PORT --db-name=NAME --db-user=USER
  --db-password=PASS     пароль логина приложения (иначе генерируется)
  --sa-password=PASS     пароль SA контейнера (иначе запрос)
  --mssql-host-port=PORT порт контейнера на localhost (1433)
  --db-trust-cert        не проверять сертификат внешнего MSSQL
  --create-db            создать базу на внешнем сервере, если нет

Администратор портала:
  --admin-user=LOGIN --admin-email=MAIL --admin-password=PASS
  --no-admin             не создавать суперпользователя

Бэкапы:
  --backup-dir=DIR --backup-schedule=CRON --backup-retention=DAYS
  --no-backup-cron

Прочее:
  --skip-firewall        не открывать порты в ufw
  --force-env            перезаписать существующий .env
  --yes                  без интерактивных подтверждений
  --check                только проверить окружение
  --dry-run              показать действия без изменений
  -h, --help             эта справка
EOF
}

# Возвращает значение опции: --opt=value или --opt value.
opt_value() {
    if [ "$1" != "${1#*=}" ]; then
        printf '%s' "${1#*=}"
    else
        printf '%s' "${2:-}"
    fi
}

while [ "$#" -gt 0 ]; do
    arg="$1"
    key="${arg%%=*}"
    has_eq=1
    if [ "$key" = "$arg" ]; then
        has_eq=0
    fi
    val="$(opt_value "$@")"

    case "$key" in
        --db) DB_MODE="$val" ;;
        --app-dir) APP_DIR="$val" ;;
        --app-user) APP_USER="$val" ;;
        --domain) DOMAIN="$val" ;;
        --tls) TLS_MODE="$val" ;;
        --cert) TLS_CERT="$val" ;;
        --key) TLS_KEY="$val" ;;
        --tls-days) TLS_DAYS="$val" ;;
        --db-host) DB_HOST="$val" ;;
        --db-port) DB_PORT="$val" ;;
        --db-name) DB_NAME="$val" ;;
        --db-user) DB_USER="$val" ;;
        --db-password) DB_PASSWORD="$val" ;;
        --sa-password) SA_PASSWORD="$val" ;;
        --mssql-host-port) MSSQL_HOST_PORT="$val" ;;
        --admin-user) ADMIN_USER="$val" ;;
        --admin-email) ADMIN_EMAIL="$val" ;;
        --admin-password) ADMIN_PASSWORD="$val" ;;
        --backup-dir) BACKUP_DIR="$val" ;;
        --backup-schedule) BACKUP_SCHEDULE="$val" ;;
        --backup-retention) BACKUP_RETENTION="$val" ;;
        --db-trust-cert) DB_TRUST_CERT="True" ;;
        --create-db) CREATE_DB=1 ;;
        --no-admin) NO_ADMIN=1 ;;
        --no-backup-cron) NO_BACKUP_CRON=1 ;;
        --skip-firewall) SKIP_FIREWALL=1 ;;
        --force-env) FORCE_ENV=1 ;;
        --allow-http) ALLOW_HTTP=1 ;;
        --yes|-y) YES=1 ;;
        --check) CHECK_ONLY=1 ;;
        --dry-run) DRY_RUN=1 ;;
        -h|--help) usage; exit 0 ;;
        *)
            printf 'Неизвестный параметр: %s\n\n' "$arg" >&2
            usage >&2
            exit 2
            ;;
    esac

    case " ${VALUE_OPTS} " in
        *" ${key} "*)
            if [ "$has_eq" -eq 0 ]; then
                if [ "$#" -lt 2 ]; then
                    printf 'Параметру %s нужно значение\n' "$key" >&2
                    exit 2
                fi
                shift
            fi
            ;;
    esac
    shift
done

# --- Служебные функции установщика -----------------------------------------

# Подключает модули установщика.
source_libs() {
    local module
    [ -f "${LIB_DIR}/common.sh" ] || {
        printf 'Не найден %s/common.sh\n' "$LIB_DIR" >&2
        exit 1
    }
    for module in common packages database app webserver services; do
        if [ ! -f "${LIB_DIR}/${module}.sh" ]; then
            printf 'Не найден %s/%s.sh\n' "$LIB_DIR" "$module" >&2
            exit 1
        fi
        # shellcheck source=/dev/null
        . "${LIB_DIR}/${module}.sh"
    done
}

# Открывает файл журнала установки.
init_logging() {
    if [ "$CHECK_ONLY" = "1" ] || [ "$DRY_RUN" = "1" ] \
        || [ "$(id -u)" -ne 0 ]; then
        LOG_FILE="${TMPDIR:-/tmp}/portal-install.log"
        : > "$LOG_FILE"
    else
        mkdir -p "$LOG_DIR"
        chmod 750 "$LOG_DIR"
        LOG_FILE="${LOG_DIR}/install-$(date +%Y%m%d-%H%M%S).log"
        : > "$LOG_FILE"
        chmod 600 "$LOG_FILE"
    fi
    printf 'Журнал установки: %s\n' "$LOG_FILE"
}

# Диагностика при неожиданном сбое.
on_error() {
    local code=$?
    printf '\n[ошибка] установка прервана (код %s), строка %s\n' \
        "$code" "${BASH_LINENO[0]}" | tee -a "$LOG_FILE" >&2
    if [ "$DRY_RUN" != "1" ] && [ "$CHECK_ONLY" != "1" ]; then
        systemctl status --no-pager -l portal 2>/dev/null \
            | tail -n 20 | tee -a "$LOG_FILE" >&2 || true
        journalctl -u portal -n 30 --no-pager 2>/dev/null \
            | tee -a "$LOG_FILE" >&2 || true
    fi
    printf 'Полный журнал: %s\n' "$LOG_FILE" >&2
}

check_root() {
    if [ "$CHECK_ONLY" = "1" ] || [ "$DRY_RUN" = "1" ]; then
        return 0
    fi
    if [ "$(id -u)" -ne 0 ]; then
        die "запускать нужно от root: sudo ${SCRIPT_DIR}/install.sh ..."
    fi
}

check_os() {
    [ -r /etc/os-release ] || die "не найден /etc/os-release"
    # shellcheck disable=SC1091
    . /etc/os-release
    case "${ID:-}" in
        ubuntu|debian) ;;
        *) die "поддерживаются Ubuntu/Debian, найдено: ${ID:-?}" ;;
    esac
    log "ОС: ${PRETTY_NAME:-${ID}}"
}

check_systemd() {
    [ -d /run/systemd/system ] \
        || die "systemd не запущен: установка служб невозможна"
}

check_python() {
    if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)'; then
        die "нужен Python 3.12+, найден: $(python3 -V 2>&1)"
    fi
    log "Python: $(python3 -V 2>&1)"
}

# Проверяет корректность параметров до любых изменений.
validate_args() {
    local path
    for path in "$APP_DIR" "$BACKUP_DIR" "$LOG_DIR"; do
        case "$path" in
            /*) ;;
            *) die "путь должен быть абсолютным: ${path}" ;;
        esac
        case "$path" in
            *" "*) die "пути с пробелами не поддерживаются: ${path}" ;;
        esac
    done
    case "$DB_NAME" in
        *[!A-Za-z0-9_]*) die "DB_NAME: только буквы, цифры и _" ;;
    esac
    case "$DB_MODE" in
        docker|external) ;;
        "") ;;
        *) die "--db должен быть docker или external" ;;
    esac
    case "$TLS_MODE" in
        selfsigned|existing|none) ;;
        *) die "--tls: selfsigned, existing или none" ;;
    esac
    if [ "$TLS_MODE" = "existing" ]; then
        if [ -z "$TLS_CERT" ] || [ -z "$TLS_KEY" ]; then
            die "--tls=existing требует --cert и --key"
        fi
    fi
    if [ "$TLS_MODE" = "none" ] && [ "$ALLOW_HTTP" != "1" ]; then
        die "режим без TLS требует явного --allow-http"
    fi
    case "$BACKUP_RETENTION" in
        ''|*[!0-9]*) die "--backup-retention должен быть числом" ;;
    esac
    case "$DOMAIN" in
        *[!A-Za-z0-9.-]*) die "домен содержит недопустимые символы" ;;
    esac
}

# Определяет режим БД: флаг, затем .env, затем интерактивный вопрос.
resolve_db_mode() {
    if [ -z "$DB_MODE" ] && [ -f "${APP_DIR}/.env" ]; then
        DB_MODE="$(env_value DEPLOY_DB_MODE "${APP_DIR}/.env")"
        if [ -n "$DB_MODE" ]; then
            log "режим БД из ${APP_DIR}/.env: ${DB_MODE}"
        fi
    fi
    if [ -z "$DB_MODE" ]; then
        if interactive; then
            printf 'Режим MS SQL Server:\n'
            printf '  1) docker   — контейнер на этом сервере\n'
            printf '  2) external — сервер MS SQL в сети\n'
            DB_MODE="$(ask 'Выбор' 'docker')"
            case "$DB_MODE" in
                1) DB_MODE="docker" ;;
                2) DB_MODE="external" ;;
            esac
        else
            die "не задан --db=docker|external"
        fi
    fi
    log "режим БД: ${DB_MODE}"
}

# Вычисляет зависимые от режимов значения.
compute_settings() {
    if [ "$TLS_MODE" = "none" ]; then
        USE_PROXY_TLS="False"
        SSL_REDIRECT="False"
        COOKIE_SECURE="False"
        HSTS_SECONDS="0"
        CSRF_ORIGINS="http://${DOMAIN}"
    else
        USE_PROXY_TLS="True"
        SSL_REDIRECT="True"
        COOKIE_SECURE="True"
        # HSTS выключен: с самоподписанным сертификатом браузер не даёт
        # обойти предупреждение, и сотрудники не смогут войти. Включать
        # (31536000) после перехода на сертификат корпоративного УЦ.
        HSTS_SECONDS="0"
        CSRF_ORIGINS="https://${DOMAIN}"
    fi
    ALLOWED_HOSTS="${DOMAIN},127.0.0.1,localhost"
    APP_HOME="/var/lib/${APP_USER}"
    MEDIA_ROOT="${APP_HOME}/media"
    ENV_FILE="${APP_DIR}/.env"

    if [ -z "$DB_TRUST_CERT" ]; then
        if [ "$DB_MODE" = "docker" ]; then
            DB_TRUST_CERT="True"
        else
            DB_TRUST_CERT="False"
        fi
    fi
}

# Проверяет пароль SA по требованиям MS SQL Server.
valid_sa_password() {
    local value="$1"
    [ "${#value}" -ge 8 ] || return 1
    [[ "$value" =~ [A-Z] ]] || return 1
    [[ "$value" =~ [a-z] ]] || return 1
    [[ "$value" =~ [0-9] ]] || return 1
    [[ "$value" =~ [^A-Za-z0-9] ]] || return 1
}

# Генерирует пароль приложения, проходящий политику SQL Server:
# заглавная буква, строчные, цифры и спецсимвол.
generate_db_password() {
    printf 'Pt!%s' "$(openssl rand -hex 16)"
}

# Запрашивает недостающие пароли.
resolve_passwords() {
    if [ "$DB_MODE" = "docker" ]; then
        # Пароль SA нужен контейнеру и административным операциям:
        # созданию базы и SQL-логина приложения.
        if [ -z "$SA_PASSWORD" ] && [ "$DB_USER" = "sa" ]; then
            SA_PASSWORD="$DB_PASSWORD"
        fi
        if [ -z "$SA_PASSWORD" ] && [ "$DRY_RUN" != "1" ]; then
            SA_PASSWORD="$(ask_password 'Пароль SA контейнера MSSQL')"
        fi
        if [ -z "$SA_PASSWORD" ] && [ "$DRY_RUN" = "1" ]; then
            SA_PASSWORD="dry-run-sa-password"
        fi
        if [ "$DRY_RUN" != "1" ] \
            && ! valid_sa_password "$SA_PASSWORD"; then
            die "пароль SA: минимум 8 символов, заглавные, строчные, цифры и спецсимвол"
        fi

        # Портал не работает под sa: у приложения свой логин с правами
        # только на его базу.
        if [ -z "$DB_USER" ] || [ "$DB_USER" = "sa" ]; then
            DB_USER="portal"
        fi
        if [ -z "$DB_PASSWORD" ]; then
            DB_PASSWORD="$(generate_db_password)"
            log "сгенерирован пароль SQL-логина ${DB_USER}"
        fi
        if [ "$DRY_RUN" != "1" ] \
            && ! valid_sa_password "$DB_PASSWORD"; then
            die "пароль ${DB_USER}: минимум 8 символов, заглавные, строчные, цифры и спецсимвол"
        fi
        return 0
    fi

    if [ -z "$DB_PASSWORD" ] && [ "$DRY_RUN" != "1" ]; then
        DB_PASSWORD="$(ask_password "Пароль MSSQL для ${DB_USER}")"
    fi
    if [ -z "$DB_PASSWORD" ] && [ "$DRY_RUN" != "1" ]; then
        die "не задан пароль MSSQL (--db-password)"
    fi
}

# Отчёт режима --check.
check_only_report() {
    local want=("${BASE_PACKAGES[@]}")
    if [ "$DB_MODE" = "docker" ]; then
        want+=("${DOCKER_PACKAGES[@]}")
    fi
    packages_missing "${want[@]}"
    if [ "${#MISSING_PACKAGES[@]}" -gt 0 ]; then
        warn "не хватает пакетов: ${MISSING_PACKAGES[*]}"
        printf 'Обычный запуск установщика добавит их.\n'
        exit 2
    fi
    log "все необходимые пакеты установлены"
    exit 0
}

# Итоговая сводка установки.
print_summary() {
    local scheme="https"
    if [ "$TLS_MODE" = "none" ]; then
        scheme="http"
    fi
    log "=============================================================="
    log "Портал установлен"
    log "  Адрес:           ${scheme}://${DOMAIN}/"
    log "  Админка:         ${scheme}://${DOMAIN}/admin/"
    log "  Каталог:         ${APP_DIR}"
    log "  Пользователь:    ${APP_USER}"
    log "  База:            ${DB_MODE} ${DB_HOST}:${DB_PORT}/${DB_NAME}"
    log "  SQL-логин:       ${DB_USER}"
    log "  Журнал службы:   journalctl -u portal"
    log "  Каталог логов:   ${LOG_DIR}"
    log "  Бэкапы:          ${BACKUP_DIR} (${BACKUP_SCHEDULE})"
    if [ "$NO_ADMIN" != "1" ]; then
        log "  Админ портала:   ${ADMIN_USER}"
    fi
    if [ "$TLS_MODE" = "selfsigned" ]; then
        warn "самоподписанный сертификат: браузер попросит подтверждение"
    fi
    log "  Журнал установки: ${LOG_FILE}"
    log "=============================================================="
}

main() {
    source_libs
    trap on_error ERR
    check_root
    init_logging
    log "запуск установщика: ${SCRIPT_DIR}/install.sh $*"

    check_os
    ensure_python
    check_python
    resolve_db_mode
    validate_args
    compute_settings

    if [ "$CHECK_ONLY" = "1" ]; then
        check_only_report
    fi
    if [ "$DRY_RUN" = "1" ]; then
        log "режим --dry-run: изменения не выполняются"
    fi

    resolve_passwords
    check_systemd
    webserver_check_ports

    packages_ensure
    app_create_user
    app_create_dirs
    app_sync_code
    app_create_venv
    app_write_env

    ENV_FILE="${APP_DIR}/.env"
    db_load_env
    db_prepare

    app_prepare_django

    services_install_unit
    webserver_prepare_tls
    webserver_configure_nginx
    webserver_firewall
    services_backup_cron
    acceptance_checks

    print_summary
}

main "$@"
