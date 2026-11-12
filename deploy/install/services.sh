# shellcheck shell=bash
# shellcheck disable=SC2034,SC2153
# Модуль подключается из install.sh в общее пространство имён,
# поэтому shellcheck не видит переменные, объявленные в соседях.
# systemd-служба, cron-бэкап и приёмочные проверки.

SYSTEMD_UNIT="/etc/systemd/system/portal.service"
CRON_FILE="/etc/cron.d/portal-backup"

# Устанавливает и запускает службу portal.
services_install_unit() {
    export T_APP_DIR="$APP_DIR"
    export T_APP_USER="$APP_USER"
    # Каталог журналов нужен службе на запись (ProtectSystem=strict).
    export T_LOG_DIR="$LOG_DIR"

    render_template \
        "${DEPLOY_DIR}/templates/portal.service.in" \
        "$SYSTEMD_UNIT"

    run systemctl daemon-reload
    run systemctl enable portal

    if systemctl is-active --quiet portal; then
        run systemctl restart portal
    else
        run systemctl start portal
    fi

    if [ "$DRY_RUN" = "1" ]; then
        return 0
    fi

    local attempt
    for attempt in $(seq 1 30); do
        if systemctl is-active --quiet portal; then
            log "служба portal активна"
            return 0
        fi
        sleep 1
    done
    die "portal не запустился: journalctl -u portal -n 50"
}

# Устанавливает запись cron для ежедневного бэкапа.
services_backup_cron() {
    if [ "$NO_BACKUP_CRON" = "1" ]; then
        log "cron-бэкап не настраивается (--no-backup-cron)"
        return 0
    fi
    if [ "$DRY_RUN" = "1" ]; then
        log "[dry-run] cron ${CRON_FILE}: ${BACKUP_SCHEDULE}"
        return 0
    fi
    # Без запущенной службы cron запись не сработает.
    run systemctl enable --now cron
    {
        printf '# Резервная копия портала (создано deploy/install.sh)\n'
        printf 'MAILTO=""\n'
        printf '%s root APP_DIR=%s BACKUP_DIR=%s RETENTION_DAYS=%s ' \
            "$BACKUP_SCHEDULE" "$APP_DIR" "$BACKUP_DIR" \
            "$BACKUP_RETENTION"
        printf '%s/deploy/backup.sh >> %s/backup.log 2>&1\n' \
            "$APP_DIR" "$LOG_DIR"
    } > "$CRON_FILE"
    chmod 644 "$CRON_FILE"
    chown root:root "$CRON_FILE"
    run chmod +x "${APP_DIR}/deploy/backup.sh"
    log "cron-бэкап установлен: ${CRON_FILE}"
}

# Проверяет конфигурацию Django и доступность портала через nginx.
acceptance_checks() {
    if [ "$DRY_RUN" = "1" ]; then
        log "[dry-run] приёмочные проверки пропущены"
        return 0
    fi

    log "проверка конфигурации Django"
    # ERROR важен: предупреждения (HSTS при самоподписанном сертификате)
    # установку не останавливают, а ошибки — останавливают.
    run_in_app "$APP_USER" venv/bin/python \
        manage.py check --deploy --fail-level=ERROR

    local scheme="http" port=80 opts=()
    if [ "$TLS_MODE" != "none" ]; then
        scheme="https"
        port=443
        opts=(-k)
    fi

    # Статику отдаёт nginx: проверяем, что права выставлены верно.
    local static_url="${scheme}://${DOMAIN}/static/css/base.css"
    if curl "${opts[@]}" -fsS --max-time 15 \
        --resolve "${DOMAIN}:${port}:127.0.0.1" "$static_url" >/dev/null; then
        log "статика доступна: ${static_url}"
    else
        die "nginx не отдаёт статику (${static_url}): проверьте права на ${APP_DIR}/staticfiles"
    fi

    # Проверка живости: приложение и база.
    local health_url="${scheme}://${DOMAIN}/healthz/"
    if curl "${opts[@]}" -fsS --max-time 15 \
        --resolve "${DOMAIN}:${port}:127.0.0.1" "$health_url" >/dev/null; then
        log "проверка живости пройдена: ${health_url}"
    else
        die "проверка живости не пройдена (${health_url}): journalctl -u portal -n 50"
    fi

    local url="${scheme}://${DOMAIN}/accounts/login/"

    if curl "${opts[@]}" -fsS --max-time 15 \
        --resolve "${DOMAIN}:${port}:127.0.0.1" "$url" >/dev/null; then
        log "портал отвечает: ${url}"
    else
        die "портал не отвечает по ${url}: journalctl -u portal -n 50"
    fi

    local service
    for service in portal nginx cron; do
        if systemctl is-active --quiet "$service"; then
            log "служба ${service}: active"
        else
            warn "служба ${service} не активна"
        fi
    done
    if [ "$DB_MODE" = "docker" ] && ! systemctl is-active --quiet docker; then
        warn "служба docker не активна"
    fi
}
