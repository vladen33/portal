# portal — внутренний портал организации

Портал для сотрудников: набор разделов, которые подключаются
отдельными приложениями Django. Сейчас готов каркас — главная
страница, общее меню и вход; разделы добавляются отдельными
итерациями.

## Стек

- Python 3.14, Django 6.1;
- SQLite 3 — локальная разработка;
- MS SQL Server — проверка на реальной СУБД и production
  (backend `mssql-django`, драйвер `mssql-python`);
- WhiteNoise — раздача статики.

## Установка

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
```

В `.env` обязательно замените `DJANGO_SECRET_KEY` и, при необходимости,
параметры подключения к БД.

## Запуск

```bash
venv/bin/python manage.py migrate
venv/bin/python manage.py createsuperuser
venv/bin/python manage.py runserver 0.0.0.0:8000
```

Портал: http://127.0.0.1:8000/ , админка: http://127.0.0.1:8000/admin/ .

## Базы данных

Профиль выбирается в `.env` переменной `DB_ENGINE`:

- `sqlite` — файл `db.sqlite3` в корне проекта (по умолчанию);
- `mssql` — параметры `DB_NAME`, `DB_USER`, `DB_PASSWORD`,
  `DB_HOST`, `DB_PORT`. Тестовый экземпляр MS SQL Server поднимается
  в Docker (`deploy/docker-compose.mssql.yml`), production — реальный
  сервер в локальной сети.

### MS SQL Server в Docker

```bash
sudo apt install -y docker.io docker-compose-v2
# Backend mssql-django импортирует pyodbc, которому нужна unixODBC.
sudo apt install -y libodbc2
sudo usermod -aG docker "$USER"        # потребуется перелогин

# в .env: MSSQL_SA_PASSWORD, DB_ENGINE=mssql, DB_USER=sa,
# DB_PASSWORD=<тот же пароль>, DB_HOST=127.0.0.1, DB_NAME=portal
docker compose -f deploy/docker-compose.mssql.yml up -d

venv/bin/python manage.py migrate
venv/bin/python -m pytest -n auto
```

Контейнер слушает только `127.0.0.1`, данные лежат в volume
`mssql-data`. Если контейнер запускается впервые, дождитесь
статуса `healthy` (примерно 30–60 секунд).

Соединение идёт через драйвер `mssql-python`
(`OPTIONS['python_driver'] = 'mssql_python'`): он входит в
`mssql-django` 2.0 и содержит собственный ODBC Driver 18, поэтому
`msodbcsql18` из репозитория Microsoft устанавливать не нужно.
Системная библиотека `libodbc2` требуется только потому, что
backend при импорте подгружает `pyodbc`.

Проверено на MS SQL Server 2022 в Docker: миграции применяются,
тесты проходят (`-n auto`).

## Установка на сервер

Установщик `deploy/install.sh` выполняет всё сам: проверяет и ставит
системные пакеты, создаёт пользователя и каталоги, копирует код,
готовит venv и `.env`, поднимает MS SQL Server, применяет миграции,
настраивает systemd, nginx с TLS, ufw и cron-бэкап.

```bash
# MS SQL Server в контейнере на этом же сервере
sudo deploy/install.sh --db=docker --domain=portal.example.local

# внешний MS SQL Server в локальной сети
sudo deploy/install.sh --db=external --db-host=10.0.0.5 \
    --db-user=portal --create-db --domain=portal.example.local

# проверка окружения и план действий без изменений
deploy/install.sh --check --db=docker
deploy/install.sh --dry-run --db=external
```

Что важно знать:

- режимы БД: `--db=docker` (контейнер на сервере, пароль SA
  запрашивается интерактивно) и `--db=external` (существующий
  сервер; база по умолчанию не создаётся — добавьте `--create-db`,
  если у пользователя есть права на DDL);
- TLS: `--tls=selfsigned` (по умолчанию), `--tls=existing
  --cert=... --key=...` или `--tls=none --allow-http`
  (не рекомендуется: пароли идут открытым текстом);
- пароли по умолчанию запрашиваются интерактивно; флаги
  `--db-password`, `--sa-password`, `--admin-password` нужны только
  для автоматизации;
- повторный запуск идемпотентен: существующий `.env` не меняется
  (перезапись — `--force-env`), миграции и группы не дублируются;
- полная справка: `deploy/install.sh --help`.

Компоненты контура: gunicorn под systemd слушает `127.0.0.1:8000`,
nginx проксирует на него по TLS и отдаёт статику. Файлы из
`MEDIA_ROOT` раздаются только Django после проверки прав доступа,
поэтому каталог размещается вне web-root nginx. Бэкапы настраиваются
cron-записью на `deploy/backup.sh` (по умолчанию ежедневно в 2:30,
хранение 30 дней).

Проверка после установки:

```bash
systemctl status portal nginx
journalctl -u portal -n 50
cd /srv/portal && venv/bin/python manage.py check --deploy
```

`check --deploy` не покажет предупреждений, если в `.env` включены
`DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS` и `DJANGO_SECURE_HSTS_PRELOAD`
(только когда все поддомены домена тоже работают по HTTPS).

Файлы из `MEDIA_ROOT` в nginx отдельной локацией не раздаются:
каталог размещается вне web-root, а доступ к файлам отдают вьюхи
приложений после проверки прав.

## Вход через Active Directory

На портале две категории пользователей:

- **локальные** (`auth_source = local`) — их вручную создаёт
  администратор портала, пароль хранится в Django; могут быть
  пользователями, staff или суперпользователями;
- **доменные** (`auth_source = ad`) — входят логином и паролем
  Active Directory. Пароль в Django не хранится, при первом успешном
  входе учётная запись портала создаётся автоматически (JIT) и
  попадает в группу `AD_DEFAULT_GROUP`.

Связь доменной и локальной учётки хранится в поле
`User.ad_login` (`sAMAccountName`) и может не совпадать с `username`.
Администратор указывает её в карточке пользователя в админке, когда
логины различаются; менять пароль доменной учётки из админки нельзя.

Порядок настройки:

```bash
# 1. Заполнить в .env: AD_ENABLED=True, AD_SERVER_URI=ldaps://...,
#    AD_BIND_DN, AD_BIND_PASSWORD, AD_USER_SEARCH_BASE,
#    AD_REQUIRED_GROUP, AD_CA_CERT_FILE
# 2. Создать группу начальных прав
venv/bin/python manage.py setup_portal_roles
# 3. Навесить на группу нужные права в админке
venv/bin/python manage.py runserver
```

Требования безопасности: пароль доменной учётки передаётся только
по `ldaps://` либо по `ldap://` + StartTLS; при небезопасной
конфигурации вход через AD блокируется (`manage.py check` выдаёт
ошибку `accounts.E001`). Сертификат контроллера домена должен быть
подписан доверенным УЦ, иначе укажите корневой сертификат
в `AD_CA_CERT_FILE`.

## Тесты и проверки кода

```bash
venv/bin/python -m pytest -n auto    # тесты параллельно на всех ядрах
venv/bin/python -m ruff check .      # линтер
venv/bin/python -m ruff format .     # форматирование
```

Правила проекта (стиль, комментарии, тестирование) описаны в
`.clinerules/project-rules.md`.

## Обновление существующей установки

Приложение `documents` из первой итерации удалено. Если база уже
развёрнута с ним, до запуска новой версии снимите приложение с базы
(данные документов и ознакомлений при этом удаляются, поэтому сначала
сделайте резервную копию):

```bash
venv/bin/python manage.py migrate documents zero
venv/bin/python manage.py remove_stale_contenttypes
```

## Структура

```
config/      настройки и корневые маршруты
accounts/    пользователь портала, backend'ы и форма входа
core/        главная страница и общая навигация
templates/   общие шаблоны (base.html, страница входа)
static/      исходная статика
media/       загруженные файлы (вне git)
deploy/      инфраструктурные файлы и установщик
```

## Реализовано

- каркас портала: главная страница и общее меню;
- вход по учётной записи портала и по учётной записи Active Directory
  (режим AD включается настройкой `AD_ENABLED`);
- JIT-создание учётной записи портала при первом входе через AD,
  связывание доменного и локального логинов полем `User.ad_login`;
- админка пользователя с кадровыми полями и источником учётной записи.

Новый раздел подключается отдельным приложением Django: маршруты —
в `config/urls.py`, ссылки — в `core/templates/core/home.html` и в меню
`templates/base.html`. Каталог `MEDIA_ROOT` уже учтён в настройках и
в инфраструктуре деплоя: разделу с загрузкой файлов останется добавить
вьюху, которая проверяет права и отдаёт файл (в production — через
`X-Accel-Redirect`).

## Известные ограничения

- для production нужен корпоративный корневой сертификат
  (`AD_CA_CERT_FILE`): самоподписанный сертификат контроллера домена
  не принимается;
- членство в доменной группе проверяется по атрибуту `memberOf`;
  основная группа пользователя (primary group) в `memberOf`
  не попадает — её нужно указывать через `AD_REQUIRED_GROUP` осознанно;
- самостоятельная регистрация и сброс пароля не предусмотрены:
  локальные учётные записи создаёт администратор.
