"""Конфигурация gunicorn для портала СМК.

Запуск (systemd передаёт рабочую директорию проекта):

    venv/bin/gunicorn --config deploy/gunicorn.conf.py config.wsgi

Gunicorn слушает unix-сокет: наружу порт не публикуется, запросы
приходят только от nginx.
"""

import multiprocessing
import os

# Сокет создаётся в /run (systemd RuntimeDirectory).
bind = os.getenv('GUNICORN_BIND', 'unix:/run/portal-ksmk/gunicorn.sock')

# Два воркера на ядро плюс один — стандартная эвристика для
# приложения, которое ждёт базу данных.
workers = int(
    os.getenv(
        'GUNICORN_WORKERS',
        str(multiprocessing.cpu_count() * 2 + 1),
    )
)
worker_class = 'sync'
timeout = int(os.getenv('GUNICORN_TIMEOUT', '60'))
graceful_timeout = 30
keepalive = 5

# Логи уходят в stdout/stderr, их собирает journald.
accesslog = '-'
errorlog = '-'
loglevel = os.getenv('GUNICORN_LOGLEVEL', 'info')

# Периодически перезапускаем воркеры, чтобы не копить утечки памяти.
max_requests = 1000
max_requests_jitter = 100

# Заголовки X-Forwarded-* подставляет только nginx на этой машине.
forwarded_allow_ips = '127.0.0.1,::1'
