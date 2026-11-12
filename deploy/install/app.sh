# shellcheck shell=bash
# shellcheck disable=SC2034,SC2153
# Модуль подключается из install.sh в общее пространство имён,
# поэтому shellcheck не видит переменные, объявленные в соседях.
# Пользователь, каталоги, код, venv и .env приложения.

APP_HOME="${APP_HOME:-/var/lib/${APP_USER}}"
ENV_FILE="${ENV_FILE:-${APP_DIR}/.env}"

# Создаёт системного пользователя приложения (без логин-шелла).
app_create_user() {
    if id -u "$APP_USER" >/dev/null 2>&1; then
        log "пользователь ${APP_USER} уже существует"
        return 0
    fi
    run useradd --system --home-dir "$APP_HOME" --create-home \
        --shell /usr/sbin/nologin "$APP_USER"
}

# Создаёт каталоги приложения, файлов, логов и бэкапов.
app_create_dirs() {
    run install -d -m 750 -o "$APP_USER" -g "$APP_USER" "$APP_DIR"
    run install -d -m 750 -o "$APP_USER" -g "$APP_USER" "$MEDIA_ROOT"
    run install -d -m 750 -o root -g root "$LOG_DIR"
    run install -d -m 700 -o root -g root "$BACKUP_DIR"
}

# Копирует код проекта в каталог установки, если он ещё не там.
app_sync_code() {
    if [ "$SOURCE_DIR" = "$APP_DIR" ]; then
        log "код уже находится в ${APP_DIR}"
        return 0
    fi
    log "копируем код: ${SOURCE_DIR} -> ${APP_DIR}"
    run rsync -a \
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
        "${SOURCE_DIR}/" "${APP_DIR}/"
    run chown -R "${APP_USER}:${APP_USER}" "$APP_DIR"
}

# Создаёт venv и устанавливает зависимости.
app_create_venv() {
    if [ -x "${APP_DIR}/venv/bin/python" ]; then
        log "venv уже создан"
    else
        run_as "$APP_USER" python3 -m venv "${APP_DIR}/venv"
    fi
    run_in_app "$APP_USER" venv/bin/python -m pip install --upgrade pip
    run_in_app "$APP_USER" venv/bin/python -m pip install -r requirements.txt
}

# Генерирует SECRET_KEY средствами Django из venv.
app_secret_key() {
    if [ "$DRY_RUN" = "1" ]; then
        printf 'dry-run-secret-key'
        return 0
    fi
    capture_in_app "$APP_USER" venv/bin/python -c \
        'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())' \
        | tail -n 1
}

# Проверяет, что в существующем .env есть обязательные ключи.
app_env_validate() {
    local key
    for key in DJANGO_SECRET_KEY DB_ENGINE DB_NAME DB_USER \
        DB_PASSWORD DB_HOST; do
        if [ -z "$(env_value "$key")" ]; then
            die "в ${ENV_FILE} не задан ${key}: запустите с --force-env"
        fi
    done
}

# Создаёт .env из шаблона или проверяет существующий.
app_write_env() {
    if [ -f "$ENV_FILE" ] && [ "$FORCE_ENV" != "1" ]; then
        log "используем существующий ${ENV_FILE}"
        app_env_validate
        return 0
    fi

    local secret
    secret="$(app_secret_key)"
    if [ "$DRY_RUN" != "1" ] && [ -z "$secret" ]; then
        die "не удалось сгенерировать DJANGO_SECRET_KEY"
    fi

    export T_SECRET_KEY="$secret"
    export T_ALLOWED_HOSTS="$ALLOWED_HOSTS"
    export T_DB_NAME="$DB_NAME"
    export T_DB_USER="$DB_USER"
    export T_DB_PASSWORD="$DB_PASSWORD"
    export T_DB_HOST="$DB_HOST"
    export T_DB_PORT="$DB_PORT"
    export T_DB_TRUST_CERT="$DB_TRUST_CERT"
    export T_DB_MODE="$DB_MODE"
    export T_USE_PROXY_TLS="$USE_PROXY_TLS"
    export T_SSL_REDIRECT="$SSL_REDIRECT"
    export T_COOKIE_SECURE="$COOKIE_SECURE"
    export T_HSTS_SECONDS="$HSTS_SECONDS"
    export T_CSRF_ORIGINS="$CSRF_ORIGINS"
    export T_MEDIA_ROOT="$MEDIA_ROOT"
    export T_APP_DIR="$APP_DIR"
    export T_SA_PASSWORD="$SA_PASSWORD"
    export T_MSSQL_HOST_PORT="$MSSQL_HOST_PORT"

    render_template \
        "${DEPLOY_DIR}/templates/env.production.in" "$ENV_FILE"

    if [ "$DRY_RUN" != "1" ]; then
        run chown "${APP_USER}:${APP_USER}" "$ENV_FILE"
        run chmod 600 "$ENV_FILE"
    fi
}

# Создаёт суперпользователя портала, если его ещё нет.
app_superuser_create() {
    if [ "$NO_ADMIN" = "1" ]; then
        log "суперпользователь не создаётся (--no-admin)"
        return 0
    fi

    local exists=""
    exists="$(capture_in_app "$APP_USER" venv/bin/python manage.py shell -c \
        'from accounts.models import User; print(int(User.objects.filter(is_superuser=True).exists()))' \
        2>/dev/null | tail -n 1)"
    if [ "$exists" = "1" ]; then
        log "суперпользователь уже существует"
        return 0
    fi

    local password="${ADMIN_PASSWORD:-}"
    if [ -z "$password" ] && [ "$DRY_RUN" != "1" ]; then
        password="$(ask_password "Пароль для ${ADMIN_USER}")"
    fi
    if [ -z "$password" ] && [ "$DRY_RUN" != "1" ]; then
        die "пустой пароль администратора"
    fi

    log "создаём суперпользователя ${ADMIN_USER} (пароль $(mask "$password"))"
    if [ "$DRY_RUN" = "1" ]; then
        log "[dry-run] createsuperuser --username ${ADMIN_USER}"
        return 0
    fi

    # shellcheck disable=SC2016
    runuser -u "$APP_USER" -- env "HOME=${APP_HOME}" \
        "DJANGO_SUPERUSER_PASSWORD=${password}" \
        bash -c 'cd "$1" && shift && exec "$@"' _ "$APP_DIR" \
        venv/bin/python manage.py createsuperuser --noinput \
        --username "$ADMIN_USER" --email "$ADMIN_EMAIL"
}

# Миграции, статика, группы портала и суперпользователь.
app_prepare_django() {
    run_in_app "$APP_USER" venv/bin/python manage.py migrate --noinput
    run_in_app "$APP_USER" venv/bin/python manage.py collectstatic --noinput
    run_in_app "$APP_USER" venv/bin/python manage.py setup_portal_roles
    app_superuser_create
}
