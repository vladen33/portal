# deploy — инфраструктурные файлы

Каталог для файлов развёртывания:

- `docker-compose.mssql.yml` — MS SQL Server в Docker для проверки
  функций, зависящих от СУБД;
- `gunicorn.conf.py` — конфигурация gunicorn для production;
- `portal-ksmk.service` — systemd unit приложения;
- `nginx-portal-ksmk.conf` — сайт nginx: TLS, статика, прокси;
- `backup.sh` — резервная копия базы MSSQL и файлов редакций.
