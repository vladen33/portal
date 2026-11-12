"""Проверка подключения к MS SQL Server и создание базы.

Скрипт запускает установщик (`deploy/install.sh`) от имени
пользователя портала, в активированном venv:

    venv/bin/python deploy/db_create.py --check
    venv/bin/python deploy/db_create.py --create
    venv/bin/python deploy/db_create.py --wait 60

Параметры берутся из ``.env`` проекта — те же, что использует Django.
"""

import argparse
import os
import sys
import time
from pathlib import Path

import mssql_python
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / '.env'


def env_flag(name, default=False):
    """Читает булеву переменную окружения."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


def encode_value(value):
    """Экранирует значение для строки подключения ODBC."""
    text = str(value)
    if ';' in text or text.strip().startswith('{'):
        return '{' + text.replace('}', '}}') + '}'
    return text


def connection_string(database):
    """Собирает строку подключения к указанной базе."""
    host = os.getenv('DB_HOST', '127.0.0.1')
    port = os.getenv('DB_PORT', '1433')
    user = os.getenv('DB_USER', 'sa')
    password = os.getenv('DB_PASSWORD', '')
    trust = env_flag('DB_TRUST_CERT', default=True)
    trust_value = 'yes' if trust else 'no'
    parts = [
        f'SERVER={host},{port}',
        f'UID={encode_value(user)}',
        f'PWD={encode_value(password)}',
        f'DATABASE={encode_value(database)}',
        'Encrypt=yes',
        f'TrustServerCertificate={trust_value}',
    ]
    return ';'.join(parts)


def connect(database, autocommit=False):
    """Открывает соединение с базой через драйвер mssql-python."""
    return mssql_python.connect(
        connection_string(database),
        autocommit=autocommit,
    )


def check_connection(database, quiet=False):
    """Проверяет, что к базе можно подключиться и выполнить запрос."""
    try:
        connection = connect(database)
        try:
            cursor = connection.cursor()
            cursor.execute('SELECT 1')
            cursor.fetchone()
        finally:
            connection.close()
    except Exception as error:
        if not quiet:
            print(f'Ошибка подключения к {database}: {error}')
        return False
    if not quiet:
        print(f'Подключение к {database}: ok')
    return True


def database_exists(name):
    """Проверяет наличие базы в экземпляре MS SQL Server."""
    connection = connect('master')
    try:
        cursor = connection.cursor()
        cursor.execute(
            'SELECT 1 FROM sys.databases WHERE name = ?',
            (name,),
        )
        return cursor.fetchone() is not None
    finally:
        connection.close()


def create_database(name):
    """Создаёт базу данных, если её ещё нет."""
    if database_exists(name):
        print(f'База {name} уже существует.')
        return True
    try:
        # CREATE DATABASE нельзя выполнять внутри транзакции,
        # поэтому соединение открываем с autocommit=True.
        connection = connect('master', autocommit=True)
        try:
            cursor = connection.cursor()
            cursor.execute(f'CREATE DATABASE [{name}]')
        finally:
            connection.close()
    except Exception as error:
        print(f'Не удалось создать базу {name}: {error}')
        return False
    print(f'База {name} создана.')
    return True


def wait_connection(database, timeout):
    """Ждёт доступности базы, опрашивая её раз в две секунды."""
    deadline = time.monotonic() + timeout
    attempt = 0
    while time.monotonic() < deadline:
        attempt += 1
        if check_connection(database, quiet=True):
            print(f'Подключение к {database} установлено (попытка {attempt}).')
            return True
        time.sleep(2)
    print(f'Не дождались доступности {database} за {timeout} с.')
    return False


def main(argv):
    """Точка входа скрипта."""
    parser = argparse.ArgumentParser(
        description='Проверка MS SQL Server и создание базы портала.',
    )
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument(
        '--check',
        action='store_true',
        help='проверить подключение к базе',
    )
    action.add_argument(
        '--create',
        action='store_true',
        help='создать базу, если её нет',
    )
    action.add_argument(
        '--wait',
        type=int,
        metavar='SECONDS',
        help='ждать доступности базы не дольше SECONDS',
    )
    args = parser.parse_args(argv[1:])

    load_dotenv(ENV_FILE)
    database = os.getenv('DB_NAME', 'portal_ksmk')

    if args.check:
        return 0 if check_connection(database) else 1
    if args.create:
        return 0 if create_database(database) else 1
    return 0 if wait_connection(database, args.wait) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
