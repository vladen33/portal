# shellcheck shell=bash
# shellcheck disable=SC2034,SC2153
# Модуль подключается из install.sh в общее пространство имён,
# поэтому shellcheck не видит переменные, объявленные в соседях.
# nginx, TLS и правила firewall.

NGINX_SITE="/etc/nginx/sites-available/portal.conf"
NGINX_ENABLED="/etc/nginx/sites-enabled/portal.conf"

# Готовит сертификаты: самоподписанные, готовые или режим без TLS.
webserver_prepare_tls() {
    case "$TLS_MODE" in
        selfsigned)
            CERT="/etc/ssl/certs/portal.crt"
            KEY="/etc/ssl/private/portal.key"
            if [ -f "$CERT" ] && [ -f "$KEY" ]; then
                log "самоподписанный сертификат уже существует"
                return 0
            fi
            log "генерируем самоподписанный сертификат для ${DOMAIN}"
            run openssl req -x509 -nodes -newkey rsa:4096 \
                -days "$TLS_DAYS" \
                -subj "/CN=${DOMAIN}" \
                -keyout "$KEY" -out "$CERT"
            run chmod 600 "$KEY"
            run chmod 644 "$CERT"
            ;;
        existing)
            CERT="$TLS_CERT"
            KEY="$TLS_KEY"
            [ -r "$CERT" ] || die "не читается сертификат ${CERT}"
            [ -r "$KEY" ] || die "не читается ключ ${KEY}"
            log "используем сертификаты: ${CERT}, ${KEY}"
            ;;
        none)
            CERT=""
            KEY=""
            warn "TLS отключён: пароли передаются по сети открытым текстом"
            ;;
        *)
            die "неизвестный режим TLS: ${TLS_MODE}"
            ;;
    esac
}

# Проверяет, что порт 80/443 не занят чужим сервисом.
webserver_check_ports() {
    local port
    for port in 80 443; do
        [ "$port" = "443" ] && [ "$TLS_MODE" = "none" ] && continue
        if port_in_use "$port" && ! systemctl is-active --quiet nginx; then
            die "порт ${port} занят другим сервисом (проверьте ss -ltnp)"
        fi
    done
}

# Рендерит конфиг сайта, включает nginx и проверяет конфигурацию.
webserver_configure_nginx() {
    local template="${DEPLOY_DIR}/templates/nginx-http.conf.in"
    if [ "$TLS_MODE" != "none" ]; then
        template="${DEPLOY_DIR}/templates/nginx-tls.conf.in"
    fi

    export T_DOMAIN="$DOMAIN"
    export T_CERT="$CERT"
    export T_KEY="$KEY"
    export T_APP_DIR="$APP_DIR"

    if [ "$DRY_RUN" != "1" ] && [ -f "$NGINX_SITE" ]; then
        run cp -a "$NGINX_SITE" \
            "${NGINX_SITE}.bak.$(date +%Y%m%d-%H%M%S)"
    fi

    render_template "$template" "$NGINX_SITE"

    if [ "$DRY_RUN" = "1" ]; then
        return 0
    fi

    run ln -sfn "$NGINX_SITE" "$NGINX_ENABLED"
    run rm -f /etc/nginx/sites-enabled/default

    if ! nginx -t 2>&1 | tee -a "$LOG_FILE"; then
        die "nginx -t не прошёл: исправьте ${NGINX_SITE} (рядом лежит .bak)"
    fi

    run systemctl enable nginx
    if systemctl is-active --quiet nginx; then
        run systemctl reload nginx
    else
        run systemctl start nginx
    fi
}

# Открывает 80/443 в ufw, если он активен.
webserver_firewall() {
    if [ "$SKIP_FIREWALL" = "1" ]; then
        log "ufw не трогаем (--skip-firewall)"
        return 0
    fi
    if ! have ufw; then
        log "ufw не установлен, правила не добавляются"
        return 0
    fi
    if ! ufw status 2>/dev/null | grep -q '^Status: active'; then
        log "ufw неактивен, правила не добавляются"
        return 0
    fi
    run ufw allow 80/tcp
    if [ "$TLS_MODE" != "none" ]; then
        run ufw allow 443/tcp
    fi
}
