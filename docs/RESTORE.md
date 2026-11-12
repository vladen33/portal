# Восстановление портала из резервной копии

Резервные копии создаёт `deploy/backup.sh` и складывает
в `/var/backups/portal`:

- `portal-<дата>.bak` — дамп базы MS SQL Server;
- `env-<дата>.bak` — копия `.env` (в ней `SECRET_KEY` и пароли);
- `media-<дата>.tar.gz` — файлы из `MEDIA_ROOT`.

Восстановление выполняется на сервере от root. Портал на время
работ останавливается.

## 1. Подготовка

```bash
sudo systemctl stop portal
sudo docker ps --filter name=portal-mssql
ls -lh /var/backups/portal/
```

Нужен пароль SA из `.env` (`MSSQL_SA_PASSWORD`). Если контейнер
MSSQL был потерян, поднять его заново и дождаться статуса `healthy`:

```bash
cd /srv/portal
sudo docker compose --env-file .env -f deploy/docker-compose.mssql.yml up -d
sudo docker inspect -f '{{.State.Health.Status}}' portal-mssql
```

## 2. Восстановление базы

```bash
STAMP=20260101-023000        # имя нужного бэкапа
sudo docker cp /var/backups/portal/portal-${STAMP}.bak \
    portal-mssql:/var/opt/mssql/backup/

# 1) узнать логические имена файлов базы
sudo docker exec -it portal-mssql \
  /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -C \
  -Q "RESTORE FILELISTONLY FROM DISK=N'/var/opt/mssql/backup/portal-${STAMP}.bak'"

# 2) восстановить базу (имена взять из вывода FILELISTONLY)
sudo docker exec -it portal-mssql \
  /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -C -Q "
    RESTORE DATABASE [portal]
      FROM DISK=N'/var/opt/mssql/backup/portal-${STAMP}.bak'
      WITH REPLACE,
        MOVE 'portal'     TO '/var/opt/mssql/data/portal.mdf',
        MOVE 'portal_log' TO '/var/opt/mssql/data/portal_log.ldf';"
```

`MOVE` обязателен: без него SQL Server попытается положить файлы
по путям исходной базы и восстановление упадёт.

## 3. Восстановление `.env`

```bash
sudo install -m 600 -o portal -g portal \
    /var/backups/portal/env-${STAMP}.bak /srv/portal/.env
```

Если восстанавливается `.env` из старой версии, проверьте наличие
новых переменных (`DJANGO_LOG_DIR`, `DJANGO_SECURE_HSTS_SECONDS=0`).

## 4. Восстановление файлов

```bash
sudo tar -C /var/lib/portal -xzf /var/backups/portal/media-${STAMP}.tar.gz
sudo chown -R portal:portal /var/lib/portal/media
```

## 5. Запуск и проверка

```bash
sudo systemctl start portal
systemctl is-active portal nginx docker
curl -k https://portal.<домен>/healthz/
```

Проверить вход пользователем и число учётных записей:

```bash
sudo docker exec portal-mssql /opt/mssql-tools18/bin/sqlcmd \
  -S localhost -U sa -C -Q "SELECT COUNT(*) FROM [portal].dbo.accounts_user"
```

Если портал не стартует — `journalctl -u portal -n 100`
и правильность `DB_*` и `MSSQL_SA_PASSWORD` в `.env`. После
восстановления базы логин приложения `portal` уже содержится в дампе.

## 6. Учебное восстановление (раз в квартал)

Проверка на отдельном контейнере, не трогая рабочий:

```bash
sudo docker run -d --name mssql-restore-test \
  -p 127.0.0.1:1434:1433 \
  -e ACCEPT_EULA=Y \
  -e MSSQL_SA_PASSWORD='<временный пароль>' \
  -e MSSQL_PID=Express \
  mcr.microsoft.com/mssql/server:2022-latest
```

Подождать `healthy`, скопировать бэкап, выполнить `RESTORE`
с `MOVE` на пути тестового контейнера, проверить `SELECT COUNT(*)`
и удалить контейнер:

```bash
sudo docker rm -f mssql-restore-test
```

Результат проверки зафиксировать в журнале эксплуатации
(дата, бэкап, кто проверял).

## 7. Что важно помнить

- Бэкапы лежат на том же сервере. Потеря диска = потеря и базы,
  и бэкапов; копию на другой хост делать минимум раз в неделю.
- `.env` содержит секреты: хранить и передавать только по защищённым
  каналам.
- Обратные миграции не выполняются: откат версии — восстановление
  базы из бэкапа, сделанного перед обновлением.
