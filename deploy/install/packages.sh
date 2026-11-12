# shellcheck shell=bash
# shellcheck disable=SC2034,SC2153
# Модуль подключается из install.sh в общее пространство имён,
# поэтому shellcheck не видит переменные, объявленные в соседях.
# Проверка и установка системных пакетов через apt.

# Пакеты, нужные при любом режиме установки.
BASE_PACKAGES=(
    python3
    python3-venv
    nginx
    rsync
    openssl
    curl
    ca-certificates
    cron
    libodbc2
    iproute2
    tar
    gzip
    util-linux
)

# Дополнительные пакеты для MSSQL в контейнере.
DOCKER_PACKAGES=(
    docker.io
    docker-compose-v2
)

# Ubuntu-базовый образ может не содержать python3: установщик
# работает на нём, поэтому ставим python3 до проверки версии.
ensure_python() {
    if have python3; then
        return 0
    fi
    if [ "$DRY_RUN" = "1" ] || [ "$CHECK_ONLY" = "1" ]; then
        warn "python3 не найден: обычный запуск установит его"
        if [ "$CHECK_ONLY" = "1" ]; then
            exit 2
        fi
        return 0
    fi
    log "python3 не найден, устанавливаем"
    run env DEBIAN_FRONTEND=noninteractive apt-get update -q
    run env DEBIAN_FRONTEND=noninteractive apt-get install -y \
        --no-install-recommends python3
    have python3 || die "не удалось установить python3"
}

# Проверяет, что пакет уже даёт нужную возможность.
# Для python3-venv имя пакета зависит от версии Python (python3.14-venv),
# поэтому проверяем наличие ensurepip: без него venv не создаётся.
package_ready() {
    case "$1" in
        python3-venv) python3 -m ensurepip --version >/dev/null 2>&1 ;;
        *) pkg_installed "$1" ;;
    esac
}

# Заполняет MISSING_PACKAGES теми пакетами из аргументов, которых нет.
packages_missing() {
    local pkg
    MISSING_PACKAGES=()
    for pkg in "$@"; do
        package_ready "$pkg" || MISSING_PACKAGES+=("$pkg")
    done
}

# Проверяет пакеты и при необходимости устанавливает недостающие.
packages_ensure() {
    local want=("${BASE_PACKAGES[@]}")
    if [ "$DB_MODE" = "docker" ]; then
        want+=("${DOCKER_PACKAGES[@]}")
    fi

    packages_missing "${want[@]}"
    if [ "${#MISSING_PACKAGES[@]}" -eq 0 ]; then
        log "все системные пакеты уже установлены"
        return 0
    fi

    log "не установлены: ${MISSING_PACKAGES[*]}"
    if [ "$DRY_RUN" = "1" ]; then
        log "[dry-run] apt-get update && apt-get install ${MISSING_PACKAGES[*]}"
        return 0
    fi

    run env DEBIAN_FRONTEND=noninteractive apt-get update -q
    run env DEBIAN_FRONTEND=noninteractive apt-get install -y \
        --no-install-recommends "${MISSING_PACKAGES[@]}"

    packages_missing "${want[@]}"
    if [ "${#MISSING_PACKAGES[@]}" -gt 0 ]; then
        die "не удалось установить пакеты: ${MISSING_PACKAGES[*]}"
    fi
    log "системные пакеты установлены"
}
