# shellcheck shell=bash
# shellcheck disable=SC2034,SC2153
# Модуль подключается из install.sh в общее пространство имён,
# поэтому shellcheck не видит переменные, объявленные в соседях.
# Подготовка MS SQL Server: контейнер на сервере или внешний сервер.

MSSQL_CONTAINER="${MSSQL_CONTAINER:-portal-ksmk-mssql}"

# Возвращает значение из .env, если оно задано, иначе текущее.
env_or() {
    local value
    value="$(env_value "$1")"
    if [ -n "$value" ]; then
        printf '%s' "$value"
    else
        printf '%s' "$2"
    fi
}

# Читает параметры подключения из .env: файл — источник истины
# при повторных запусках, флаги используются только при создании.
db_load_env() {
    DB_HOST="$(env_or DB_HOST "$DB_HOST")"
    DB_PORT="$(env_or DB_PORT "$DB_PORT")"
    DB_NAME="$(env_or DB_NAME "$DB_NAME")"
    DB_USER="$(env_or DB_USER "$DB_USER")"
    DB_PASSWORD="$(env_or DB_PASSWORD "$DB_PASSWORD")"
    MSSQL_HOST_PORT="$(env_or MSSQL_HOST_PORT "$MSSQL_HOST_PORT")"
}

# Проверяет, занят ли TCP-порт на локальной машине.
port_in_use() {
    ss -ltn 2>/dev/null | grep -q ":$1 "
}

# Запускает контейнер MSSQL и ждёт статус healthy.
db_start_docker() {
    log "режим БД: MS SQL Server в Docker"
    run systemctl enable --now docker

    if docker ps --filter "name=^/${MSSQL_CONTAINER}$" \
        --format '{{.Names}}' 2>/dev/null | grep -q .; then
        log "контейнер ${MSSQL_CONTAINER} уже запущен"
    else
        if port_in_use "$MSSQL_HOST_PORT"; then
            die "порт ${MSSQL_HOST_PORT} занят: задайте MSSQL_HOST_PORT"
        fi
        run docker compose \
            --env-file "$ENV_FILE" \
            -f "$APP_DIR/deploy/docker-compose.mssql.yml" \
            up -d
    fi

    if [ "$DRY_RUN" = "1" ]; then
        log "[dry-run] ожидание статуса healthy"
        return 0
    fi

    log "ждём готовности MSSQL (до 120 с)"
    local attempt status
    for attempt in $(seq 1 60); do
        status="$(docker inspect -f '{{.State.Health.Status}}' \
            "$MSSQL_CONTAINER" 2>/dev/null || true)"
        if [ "$status" = "healthy" ]; then
            log "MSSQL готов"
            return 0
        fi
        sleep 2
    done
    die "MSSQL не стал healthy: docker logs ${MSSQL_CONTAINER}"
}

# Создаёт базу в контейнере MSSQL.
# Используем драйвер mssql-python, а не sqlcmd: пароль не попадает
# в аргументы процесса и в журнал установки.
db_create_in_container() {
    log "создание базы ${DB_NAME} (пароль через .env)"
    run_in_app "$APP_USER" venv/bin/python deploy/db_create.py --create
}

# Ждёт, пока внешний сервер начнёт принимать TCP-соединения.
db_wait_tcp() {
    log "проверка доступности ${DB_HOST}:${DB_PORT}"
    if [ "$DRY_RUN" = "1" ]; then
        log "[dry-run] timeout 2 bash -c '</dev/tcp/${DB_HOST}/${DB_PORT}'"
        return 0
    fi
    local attempt
    for attempt in $(seq 1 20); do
        if timeout 2 bash -c "</dev/tcp/${DB_HOST}/${DB_PORT}" \
            2>/dev/null; then
            log "порт ${DB_PORT} доступен"
            return 0
        fi
        sleep 1
    done
    die "не удалось подключиться к ${DB_HOST}:${DB_PORT} (проверьте сеть, firewall, VPN)"
}

# Проверяет подключение к базе средствами драйвера mssql-python.
db_verify() {
    log "проверка подключения драйвером к базе ${DB_NAME}"
    run_in_app "$APP_USER" venv/bin/python \
        deploy/db_create.py --check
}

# Создаёт базу на внешнем сервере (флаг --create-db).
db_create_external() {
    log "создание базы ${DB_NAME} на внешнем сервере"
    run_in_app "$APP_USER" venv/bin/python \
        deploy/db_create.py --create
}

# Полная подготовка базы в зависимости от режима.
db_prepare() {
    if [ "$DB_MODE" = "docker" ]; then
        db_start_docker
        db_create_in_container
    else
        db_wait_tcp
        if [ "$CREATE_DB" = "1" ]; then
            db_create_external
        fi
    fi
    db_verify
}
