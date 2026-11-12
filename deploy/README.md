# deploy — инфраструктурные файлы

- `install.sh` — установщик production-контура (см. `--help`);
- `update.sh` — обновление установленного портала до новой версии
  кода: бэкап, остановка службы, миграции, приёмка, запуск;
- `install/` — модули установщика: пакеты, база, приложение,
  веб-сервер, службы;
- `templates/` — шаблоны `.env`, systemd-юнита и конфигов nginx
  с плейсхолдерами `@KEY@`;
- `render.py` — рендер шаблонов значениями из `T_*`;
- `db_create.py` — проверка подключения к MSSQL и создание базы;
- `docker-compose.mssql.yml` — MS SQL Server в Docker;
- `gunicorn.conf.py` — конфигурация gunicorn;
- `backup.sh` — резервная копия базы MSSQL и файлов из `MEDIA_ROOT`;
- `README.md` — этот файл.
