# shellcheck shell=bash
# shellcheck disable=SC2034,SC2153
# Модуль подключается из install.sh в общее пространство имён,
# поэтому shellcheck не видит переменные, объявленные в соседях.
# Общие функции установщика: логи, запуск команд, рендер шаблонов.
# Файл подключается из deploy/install.sh, отдельно не запускается.

LOG_FILE="${LOG_FILE:-/dev/null}"
DRY_RUN="${DRY_RUN:-0}"
DRY_RUN_DIR="${DRY_RUN_DIR:-/tmp/portal-dryrun}"
LIB_DIR="${LIB_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
RENDER_SCRIPT="$(cd "${LIB_DIR}/.." && pwd)/render.py"

# Пишет строку в лог и на экран.
log() {
    printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*" | tee -a "$LOG_FILE"
}

# Пишет предупреждение.
warn() {
    printf '[%s] ВНИМАНИЕ: %s\n' "$(date +%H:%M:%S)" "$*" \
        | tee -a "$LOG_FILE" >&2
}

# Завершает установку с сообщением об ошибке.
die() {
    printf '[%s] ОШИБКА: %s\n' "$(date +%H:%M:%S)" "$*" \
        | tee -a "$LOG_FILE" >&2
    exit 1
}

# Выполняет команду; в режиме --dry-run только печатает её.
run() {
    if [ "$DRY_RUN" = "1" ]; then
        log "[dry-run] $*"
        return 0
    fi
    log "+ $*"
    "$@"
}

# Выполняет команду от имени системного пользователя приложения.
run_as() {
    local user="$1"
    shift
    run runuser -u "$user" -- env "HOME=/var/lib/${user}" "$@"
}

# Выполняет команду в каталоге приложения от имени его пользователя.
run_in_app() {
    local user="$1"
    shift
    if [ "$DRY_RUN" = "1" ]; then
        log "[dry-run] (cd ${APP_DIR} && ${user}) $*"
        return 0
    fi
    log "+ (cd ${APP_DIR}) $*"
    # shellcheck disable=SC2016
    runuser -u "$user" -- env "HOME=/var/lib/${user}" \
        bash -c 'cd "$1" && shift && exec "$@"' _ "$APP_DIR" "$@"
}

# Возвращает stdout команды, выполненной от имени пользователя.
capture_in_app() {
    local user="$1"
    shift
    if [ "$DRY_RUN" = "1" ]; then
        return 0
    fi
    # shellcheck disable=SC2016
    runuser -u "$user" -- env "HOME=/var/lib/${user}" \
        bash -c 'cd "$1" && shift && exec "$@"' _ "$APP_DIR" "$@"
}

# Проверяет наличие команды в PATH.
have() {
    command -v "$1" >/dev/null 2>&1
}

# Проверяет, установлен ли apt-пакет.
pkg_installed() {
    dpkg-query -W -f='${Status}' "$1" 2>/dev/null \
        | grep -q 'install ok installed'
}

# Есть ли интерактивная консоль для вопросов.
interactive() {
    [ "$YES" = "0" ] && [ -t 0 ] && [ -t 1 ]
}

# Спрашивает строку с значением по умолчанию.
ask() {
    local prompt="$1" default="${2:-}" answer=""
    if ! interactive; then
        printf '%s' "$default"
        return 0
    fi
    read -r -p "$prompt [${default}]: " answer
    printf '%s' "${answer:-$default}"
}

# Спрашивает пароль без эха.
ask_password() {
    local prompt="$1" answer=""
    if ! interactive; then
        die "нет интерактивной консоли для пароля (${prompt})"
    fi
    read -r -s -p "${prompt}: " answer
    printf '\n' >&2
    printf '%s' "$answer"
}

# Маскирует секрет для вывода в лог.
mask() {
    local value="$1"
    if [ -z "$value" ]; then
        printf '<пусто>'
    else
        printf '***%s' "${value: -1}"
    fi
}

# Читает значение ключа из .env без исполнения файла.
env_value() {
    local key="$1" file="${2:-$ENV_FILE}"
    grep -E "^${key}=" "$file" 2>/dev/null \
        | tail -n 1 \
        | cut -d= -f2- \
        | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//"
}

# Рендерит шаблон из deploy/templates в целевой файл.
# Значения передаются через переменные окружения T_<KEY>.
render_template() {
    local src="$1" dst="$2" target="$2"
    [ -f "$src" ] || die "не найден шаблон ${src}"
    if [ "$DRY_RUN" = "1" ]; then
        mkdir -p "$DRY_RUN_DIR"
        target="${DRY_RUN_DIR}/$(basename "$dst")"
    fi
    log "рендер $(basename "$src") -> ${target}"
    python3 "$RENDER_SCRIPT" "$src" "$target"
}
