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
import re
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


def connection_string(database, user=None, password=None):
    """Собирает строку подключения к указанной базе.

    Аргументы ``user`` и ``password`` позволяют подключиться под другой
    учётной записью: административные операции (создание базы и логина)
    выполняются под ``sa``, а проверка — под логином приложения.
    """
    host = os.getenv('DB_HOST', '127.0.0.1')
    port = os.getenv('DB_PORT', '1433')
    if user is None:
        user = os.getenv('DB_USER', 'sa')
    if password is None:
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


def sa_credentials():
    """Возвращает логин и пароль администратора экземпляра.

    Пароль SA хранится в ``MSSQL_SA_PASSWORD``. Если он не задан,
    используется ``DB_PASSWORD`` — так работали старые установки,
    где приложение подключалось под ``sa``.
    """
    password = os.getenv('MSSQL_SA_PASSWORD', '')
    if not password:
        password = os.getenv('DB_PASSWORD', '')
    return 'sa', password


def connect(database, autocommit=False, user=None, password=None):
    """Открывает соединение с базой через драйвер mssql-python."""
    return mssql_python.connect(
        connection_string(database, user=user, password=password),
        autocommit=autocommit,
    )


def sa_connect(database, autocommit=False):
    """Открывает соединение под администратором экземпляра (sa)."""
    user, password = sa_credentials()
    return connect(
        database,
        autocommit=autocommit,
        user=user,
        password=password,
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
    connection = sa_connect('master')
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
        connection = sa_connect('master', autocommit=True)
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


def quote_name(value):
    """Проверяет имя объекта SQL Server и оборачивает его в скобки.

    Имена нельзя передать параметром в DDL-инструкции, поэтому
    подставляем в текст запроса — но только после строгой проверки.
    """
    if not re.fullmatch(r'[A-Za-z0-9_]+', value or ''):
        raise SystemExit(f'Недопустимое имя объекта SQL Server: {value!r}')
    return f'[{value}]'


def quote_password(value):
    """Экранирует пароль как строковый литерал T-SQL."""
    return "N'" + value.replace("'", "''") + "'"


def ensure_login():
    """Создаёт SQL-логин приложения и права только на его базу.

    Портал не должен работать под ``sa``: компрометация приложения
    не должна давать доступ ко всему экземпляру MS SQL Server.
    Операция идемпотентна — повторный запуск ничего не ломает.
    Учётные данные берутся из ``.env``: ``DB_USER`` и ``DB_PASSWORD``.
    """
    database = os.getenv('DB_NAME', 'portal')
    user = (os.getenv('DB_USER') or '').strip()
    password = os.getenv('DB_PASSWORD', '')

    if not user or not password:
        print('Для создания логина нужны DB_USER и DB_PASSWORD в .env.')
        return False
    if user.lower() == 'sa':
        print('DB_USER=sa: отдельный логин приложения не требуется.')
        return True

    login = quote_name(user)
    try:
        # 1. Логин уровня экземпляра.
        connection = sa_connect('master', autocommit=True)
        try:
            cursor = connection.cursor()
            cursor.execute(
                'SELECT 1 FROM sys.sql_logins WHERE name = ?',
                (user,),
            )
            if cursor.fetchone() is None:
                cursor.execute(
                    f'CREATE LOGIN {login} WITH PASSWORD = '
                    f'{quote_password(password)}, '
                    'CHECK_POLICY = ON, CHECK_EXPIRATION = OFF'
                )
                print(f'Логин {user} создан.')
            else:
                print(f'Логин {user} уже существует.')
        finally:
            connection.close()

        # 2. Пользователь базы и права владельца только этой базы.
        connection = sa_connect(quote_name(database), autocommit=True)
        try:
            cursor = connection.cursor()
            cursor.execute(
                'SELECT 1 FROM sys.database_principals WHERE name = ?',
                (user,),
            )
            if cursor.fetchone() is None:
                cursor.execute(f'CREATE USER {login} FOR LOGIN {login}')
                print(f'Пользователь {user} создан в базе {database}.')
            cursor.execute(
                'SELECT 1 '
                'FROM sys.database_role_members AS m '
                'JOIN sys.database_principals AS r '
                '  ON r.principal_id = m.role_principal_id '
                'JOIN sys.database_principals AS u '
                '  ON u.principal_id = m.member_principal_id '
                "WHERE r.name = 'db_owner' AND u.name = ?",
                (user,),
            )
            if cursor.fetchone() is None:
                cursor.execute(f'ALTER ROLE db_owner ADD MEMBER {login}')
                print(f'Роль db_owner назначена {user}.')
        finally:
            connection.close()
    except Exception as error:
        print(f'Не удалось настроить логин {user}: {error}')
        return False

    print(f'Логин приложения {user} готов.')
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
        '--ensure-login',
        action='store_true',
        help='создать SQL-логин приложения с правами на его базу',
    )
    action.add_argument(
        '--wait',
        type=int,
        metavar='SECONDS',
        help='ждать доступности базы не дольше SECONDS',
    )
    args = parser.parse_args(argv[1:])

    # interpolate=False: пароль с символом $ не должен раскрываться.
    load_dotenv(ENV_FILE, interpolate=False)
    database = os.getenv('DB_NAME', 'portal')

    if args.check:
        return 0 if check_connection(database) else 1
    if args.create:
        return 0 if create_database(database) else 1
    if args.ensure_login:
        return 0 if ensure_login() else 1
    return 0 if wait_connection(database, args.wait) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
