# portal-ksmk — портал документов СМК

Веб-приложение для работы с документами системы менеджмента качества:
карточки документов, их редакции, просмотр и фиксация ознакомления
сотрудников.

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
# DB_PASSWORD=<тот же пароль>, DB_HOST=127.0.0.1, DB_NAME=portal_ksmk
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
29 тестов проходят (`-n auto`), ограничение «одна действующая
редакция» создаётся фильтрованным уникальным индексом
`WHERE [is_current]=(1)`, поиск по кириллице регистронезависим.

## Production-контур

Компоненты: gunicorn (systemd) → unix-сокет → nginx (TLS, статика),
Django с `DEBUG=False`, MS SQL Server в локальной сети.

1. Разместить проект в `/srv/portal-ksmk`, создать пользователя
   `portal`, установить зависимости в `venv`, заполнить `.env`
   (образец — `.env.example`, раздел «Production-контур»).
2. Создать каталоги вне web-root nginx и выдать права пользователю
   `portal`:

```bash
sudo mkdir -p /var/lib/portal-ksmk/media /var/log/portal-ksmk
sudo chown -R portal:portal /var/lib/portal-ksmk
```

3. Собрать статику и применить миграции от имени пользователя
   `portal`:

```bash
cd /srv/portal-ksmk
venv/bin/python manage.py collectstatic --noinput
venv/bin/python manage.py migrate
venv/bin/python manage.py setup_portal_roles
venv/bin/python manage.py check --deploy
```

4. Установить unit и конфиг nginx:

```bash
sudo cp deploy/portal-ksmk.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now portal-ksmk

sudo cp deploy/nginx-portal-ksmk.conf \
    /etc/nginx/sites-available/portal-ksmk.conf
sudo ln -s /etc/nginx/sites-available/portal-ksmk.conf \
    /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

5. Бэкапы: `deploy/backup.sh` делает `BACKUP DATABASE` через
   `sqlcmd` в контейнере/на сервере MSSQL, архивирует `MEDIA_ROOT`
   и удаляет копии старше `RETENTION_DAYS` (30 по умолчанию).
   Пример записи в cron:

```
30 2 * * * /srv/portal-ksmk/deploy/backup.sh >> /var/log/portal-ksmk-backup.log 2>&1
```

Файлы редакций в nginx отдельной локацией не раздаются: их отдаёт
`RevisionFileView` после проверки входа. Локация
`/documents/.../file/` проксируется с выключенной буферизацией,
чтобы большие файлы шли потоком.

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

## Структура

```
config/      настройки и корневые маршруты
accounts/    пользователь портала, backend и форма входа
documents/   документы, редакции, ознакомление
templates/   общие шаблоны (base.html, страница входа)
static/      исходная статика
media/       загруженные файлы редакций (вне git)
deploy/      инфраструктурные файлы (MSSQL в Docker)
```

## Реализовано в первой итерации

- вход по учётной записи портала и по учётной записи Active Directory
  (режим AD включается настройкой `AD_ENABLED`);
- JIT-создание учётной записи портала при первом входе через AD,
  связывание доменного и локального логинов полем `User.ad_login`;
- список действующих документов с поиском и фильтром по типу;
- карточка документа со списком редакций;
- файлы редакций отдаются только через `RevisionFileView`:
  проверяется вход, фиксируется просмотр, файл нельзя скачать
  по прямой ссылке из `MEDIA_URL`;
- фиксация просмотра и ознакомления с действующей редакцией;
- админка документов, редакций и фактов ознакомления.

## Доступ к файлам редакций

`MEDIA_URL` намеренно не раздаётся ни Django (`static()`), ни nginx:
все файлы идут через вьюху `/documents/<pk>/revisions/<pk>/file/`,
которая требует авторизации и отмечает `viewed_at`. В production
каталог `MEDIA_ROOT` следует разместить вне web-root nginx, иначе
файлы можно будет получить напрямую по URL. Для больших файлов
в production вьюху можно переключить на `X-Accel-Redirect`
(nginx `internal`-локация) — меняется только отдача в
`RevisionFileView`, остальной код не затрагивается.

## Известные ограничения

- для production нужен корпоративный корневой сертификат
  (`AD_CA_CERT_FILE`): самоподписанный сертификат контроллера домена
  не принимается;
- членство в доменной группе проверяется по атрибуту `memberOf`;
  основная группа пользователя (primary group) в `memberOf`
  не попадает — её нужно указывать через `AD_REQUIRED_GROUP` осознанно;
- самостоятельная регистрация и сброс пароля не предусмотрены:
  локальные учётные записи создаёт администратор.
