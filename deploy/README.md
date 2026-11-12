# deploy — инфраструктурные файлы

- `install.sh` — установщик production-контура (см. `--help`);
- `install/` — модули установщика: пакеты, база, приложение,
  веб-сервер, службы;
- `templates/` — шаблоны `.env`, systemd-юнита и конфигов nginx
  с плейсхолдерами `@KEY@`;
- `render.py` — рендер шаблонов значениями из `T_*`;
- `db_create.py` — проверка подключения к MSSQL и создание базы;
- `docker-compose.mssql.yml` — MS SQL Server в Docker;
- `gunicorn.conf.py` — конфигурация gunicorn;
- `backup.sh` — резервная копия базы MSSQL и файлов редакций;
- `README.md` — этот файл.
