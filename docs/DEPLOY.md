# Развёртывание портала на сервере

Инструкция рассчитана на первую установку силами junior DevOps:
одна виртуальная машина в локальной сети, доступ из интернета
не требуется. Все команды выполняются на сервере, а не на машине
разработчика.

## 1. Что понадобится

- Ubuntu 26.04 LTS (minimal), статический IP.
- DNS-запись `portal.<домен>` в локальном DNS — портал открывается
  только по имени, по IP Django ответит 400.
- MS SQL Server Express в Docker на этой же машине (режим
  `--db=docker`). Внешний MS SQL — на потом.
- Сертификат: на первом этапе самоподписанный с SAN, HSTS выключен.
- Решение по админской подсети: пока `/admin/` открыт всей локальной
  сети (принятый риск), защита — сильный пароль и `limit_req`.

Проверить версии на сервере:

```bash
python3 -V          # ожидаем 3.14.x
apt-cache policy libodbc2 python3-venv docker-compose-v2
```

## 2. Подготовка ОС

```bash
sudo apt update && sudo apt -y full-upgrade
sudo timedatectl set-timezone Europe/Moscow
timedatectl status                      # синхронизация времени включена
sudo apt -y install unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
```

## 3. SSH и firewall

Сначала залить SSH-ключ и **проверить вход новой сессией**. Затем:

```bash
sudo sed -i 's/^#*PermitRootLogin.*/PermitRootLogin no/' \
    /etc/ssh/sshd_config
sudo sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' \
    /etc/ssh/sshd_config
sudo sshd -t && sudo systemctl reload ssh

sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow from 192.168.0.0/16 to any port 22 proto tcp
sudo ufw allow from 192.168.0.0/16 to any port 80 proto tcp
sudo ufw allow from 192.168.0.0/16 to any port 443 proto tcp
sudo ufw enable
sudo ufw status verbose
```

Подсеть заменить на свою. Правило для SSH добавляется **первым**,
вторую сессию держать открытой до успешной проверки.

## 4. Код и установщик

Клонируем тег в отдельный каталог: установщик сам скопирует код
в `/srv/portal` и выставит владельца. Если клонировать сразу
в `/srv/portal`, установщик пропустит копирование и `chown`,
и venv не создастся.

```bash
sudo git clone --branch v0.1.0 --depth 1 <repo-url> /opt/portal-release
cd /opt/portal-release

# только проверка окружения и план действий
sudo deploy/install.sh --check --db=docker --domain=portal.<домен>
sudo deploy/install.sh --dry-run --db=docker --domain=portal.<домен>

# установка
sudo deploy/install.sh --db=docker --domain=portal.<домен>
```

Установщик создаст:

- пользователя `portal` и каталоги `/srv/portal`,
  `/var/lib/portal/media`, `/var/log/portal`,
  `/var/backups/portal`;
- `.env` с правами 600 и сгенерированным `DJANGO_SECRET_KEY`;
- venv и зависимости;
- контейнер MS SQL Express, базу `portal` и отдельный SQL-логин
  `portal` (не `sa`);
- systemd-службу `portal`, nginx с TLS, cron-бэкап и запись
  в `ufw`.

Пароль SA запрашивается интерактивно и сохраняется в `.env`.
Пароль SQL-логина приложения генерируется автоматически.

## 5. Проверки после установки

```bash
systemctl status portal nginx docker --no-pager
journalctl -u portal -n 50

# статика (отдаёт nginx)
curl -kI https://portal.<домен>/static/css/base.css
curl -kI https://portal.<домен>/static/admin/css/base.css

# проверка живости: приложение и база
curl -k https://portal.<домен>/healthz/

# HSTS выключен — заголовка быть не должно
curl -kI https://portal.<домен>/ | grep -i strict-transport \
    || echo 'HSTS off: ok'

# сертификат содержит SAN
openssl x509 -in /etc/ssl/certs/portal.crt -noout -text \
    | grep -A1 'Subject Alternative Name'

# проверка конфигурации Django
cd /srv/portal && venv/bin/python manage.py check --deploy
```

Ожидаемое предупреждение `check --deploy`: W004 — HSTS выключен,
пока сертификат самоподписанный (W005/W021 появятся, когда HSTS
включат, но поддомены и preload не настроят). Ошибок (`ERROR`) быть
не должно.

Раздать сотрудникам корневой сертификат `/etc/ssl/certs/portal.crt`:
на Windows — `certutil -addstore -f Root portal.crt` от имени
администратора или через GPO; на Linux — скопировать в
`/usr/local/share/ca-certificates/` и выполнить
`update-ca-certificates`.

## 6. Бэкапы

Установщик добавляет cron-запись `/etc/cron.d/portal-backup`
(ежедневно в 2:30, хранение 30 дней). Проверить вручную:

```bash
sudo /srv/portal/deploy/backup.sh
ls -lh /var/backups/portal/
```

В каталоге появляются дамп базы (`portal-<дата>.bak`), копия `.env`
(`env-<дата>.bak`) и архив `media-<дата>.tar.gz`.

**Принятый риск:** копии лежат на той же машине. Минимум раз в неделю
копировать каталог на другой хост:

```bash
rsync -a /var/backups/portal/ admin@nas:<путь>/portal/
```

Раз в квартал — учебное восстановление по `docs/RESTORE.md`.

## 7. Мониторинг

Простейший вариант — cron-скрипт раз в 5 минут:

```bash
#!/usr/bin/env bash
set -euo pipefail
curl -fsSk --max-time 5 https://portal.<домен>/healthz/ >/dev/null
systemctl is-active --quiet portal nginx docker
df -h /var/backups | awk 'NR==2 {if ($5+0 > 80) exit 1}'
```

При ошибке скрипт завершается с ненулевым кодом — cron отправит
письмо (если настроен `MAILTO`) или отметит ошибку в журнале.

## 8. Обновление

Из каталога новой версии (клона тега), от root:

```bash
sudo /opt/portal-release/deploy/update.sh
```

Скрипт делает бэкап, останавливает службу, копирует код, ставит
зависимости, применяет миграции, собирает статику, проверяет
настройки, запускает службу и проверяет `/healthz/`. При ошибке
служба запускается обратно, а в консоль выводится путь к бэкапу.

Обратные миграции не выполняются: откат — восстановление базы из
бэкапа по `docs/RESTORE.md`.

## 9. Частые проблемы

| Симптом | Что проверить |
|---|---|
| `400 Bad Request` | обращение по IP; нужен домен из `DJANGO_ALLOWED_HOSTS` |
| Нет CSS на портале/в админке | `curl` на `/static/...`, права на `/srv/portal/staticfiles`, `nginx -t` |
| `/healthz/` отдаёт 503 | `docker ps`, `docker logs portal-mssql`, `journalctl -u portal -n 50` |
| Служба не стартует | `journalctl -u portal -n 100`, права на `/var/log/portal`, `.env` |
| Бэкап молчит | `sudo /srv/portal/deploy/backup.sh` вручную, `/var/log/portal/backup.log` |
| Сертификат не принимается | SAN в сертификате, сертификат установлен в доверенные |

## 10. Отложено на следующие этапы

- Вход через Active Directory — модуль готов, включается настройками
  (см. README, раздел про AD).
- Ограничение `/admin/` по админским подсетям.
- Бэкапы на NAS/вне сервера.
- Сертификат корпоративного УЦ и включение HSTS.
- CI и автоматический выкат.
