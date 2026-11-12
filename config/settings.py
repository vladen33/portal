"""Настройки проекта portal-ksmk — портала документов СМК.

Проект работает с двумя СУБД:

* SQLite 3 — быстрая локальная разработка;
* MS SQL Server — проверка на реальной СУБД и production.

Профиль выбирается переменной окружения ``DB_ENGINE``. Значения
переменных читаются из файла ``.env`` рядом с ``manage.py``
(образец — ``.env.example``).
"""

import os
from pathlib import Path

from django.contrib.messages import constants as message_constants
from dotenv import load_dotenv

# Базовый каталог проекта: /home/vlad/Dev/portal-ksmk.
BASE_DIR = Path(__file__).resolve().parent.parent

# Загружаем переменные из .env. Если файла нет, используются
# значения из окружения процесса и значения по умолчанию ниже.
load_dotenv(BASE_DIR / '.env')


def env_bool(name, default=False):
    """Приводит переменную окружения к bool.

    Истиной считаются значения ``1``, ``true``, ``yes``, ``on``
    в любом регистре.
    """
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


def env_list(name, default=''):
    """Разбирает строку вида ``a,b,c`` в список без пустых значений."""
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(',') if item.strip()]


def env_int(name, default=0):
    """Читает целое число из окружения, не падая на пустом значении."""
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return int(value)


# --- Безопасность -----------------------------------------------------------

# Секретный ключ хранится только в .env, а не в репозитории.
SECRET_KEY = os.getenv(
    'DJANGO_SECRET_KEY',
    'dev-insecure-key-change-me',
)

# Локально DEBUG=True; на production обязательно False.
DEBUG = env_bool('DJANGO_DEBUG', default=True)

ALLOWED_HOSTS = env_list(
    'DJANGO_ALLOWED_HOSTS',
    '127.0.0.1,localhost',
)

# --- Настройки production-контура ------------------------------------------

# За nginx Django узнаёт про HTTPS из заголовка X-Forwarded-Proto,
# который выставляет reverse proxy.
USE_PROXY_TLS = env_bool('DJANGO_USE_PROXY_TLS', default=not DEBUG)
if USE_PROXY_TLS:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Домены, с которых разрешены POST-запросы (если портал открыт
# не только по своему основному имени).
CSRF_TRUSTED_ORIGINS = env_list('DJANGO_CSRF_TRUSTED_ORIGINS', '')

# Редирект http -> https. За nginx включаем вместе с USE_PROXY_TLS.
SECURE_SSL_REDIRECT = env_bool(
    'DJANGO_SECURE_SSL_REDIRECT',
    default=False,
)

# Cookie сессии и CSRF передаются только по HTTPS.
SESSION_COOKIE_SECURE = env_bool(
    'DJANGO_SESSION_COOKIE_SECURE',
    default=not DEBUG,
)
CSRF_COOKIE_SECURE = env_bool(
    'DJANGO_CSRF_COOKIE_SECURE',
    default=not DEBUG,
)

# HSTS включаем один год только для production (после настройки TLS).
SECURE_HSTS_SECONDS = env_int(
    'DJANGO_SECURE_HSTS_SECONDS',
    default=31536000 if not DEBUG else 0,
)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool(
    'DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS',
    default=False,
)
SECURE_HSTS_PRELOAD = env_bool(
    'DJANGO_SECURE_HSTS_PRELOAD',
    default=False,
)

# --- Приложения -------------------------------------------------------------

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Локальные приложения проекта.
    'accounts',
    'documents',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # WhiteNoise раздаёт статику без отдельного веб-сервера.
    # Порядок важен: middleware стоит сразу после SecurityMiddleware.
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        # Общие шаблоны проекта (base.html, страница входа).
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# --- База данных ------------------------------------------------------------

# Профиль БД: sqlite (разработка) или mssql (MS SQL Server).
DB_ENGINE = os.getenv('DB_ENGINE', 'sqlite').strip().lower()

if DB_ENGINE == 'mssql':
    DATABASES = {
        'default': {
            # Драйвер от Microsoft — pip-пакет mssql-django.
            'ENGINE': 'mssql',
            'NAME': os.getenv('DB_NAME', 'portal_ksmk'),
            'USER': os.getenv('DB_USER', 'sa'),
            'PASSWORD': os.getenv('DB_PASSWORD', ''),
            'HOST': os.getenv('DB_HOST', '127.0.0.1'),
            'PORT': os.getenv('DB_PORT', '1433'),
            'OPTIONS': {
                # Драйвер mssql-python идёт вместе с mssql-django 2.0
                # и несёт собственный ODBC Driver 18, поэтому
                # msodbcsql18 из репозитория Microsoft не нужен.
                'python_driver': 'mssql_python',
                # Контейнер MSSQL в Docker использует самоподписанный
                # сертификат (DB_TRUST_CERT=True). Для внешнего сервера
                # с нормальным сертификатом ставим False.
                'extra_params': (
                    'TrustServerCertificate=yes'
                    if env_bool('DB_TRUST_CERT', default=True)
                    else 'TrustServerCertificate=no'
                ),
            },
        },
    }
    # Пул соединений управляется драйвером; для разработки и тестов
    # он отключён, чтобы не мешать пересозданию тестовой БД.
    DATABASE_CONNECTION_POOLING = False
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        },
    }

# --- Аутентификация ---------------------------------------------------------

# Кастомная модель пользователя. Указывается до первой миграции:
# заменить её потом крайне сложно.
AUTH_USER_MODEL = 'accounts.User'

# Список backend'ов собирается ниже, после настроек Active Directory:
# PortalBackend обслуживает локальные учётные записи, ADBackend —
# доменные (включается только при AD_ENABLED=True).

LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/documents/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

# --- Active Directory -------------------------------------------------------

# Вход через AD включается только явно, после настройки домена.
AD_ENABLED = env_bool('AD_ENABLED', default=False)

# Адрес каталога. Пароли доменных учётных записей должны идти
# только по шифрованному каналу: ldaps:// либо ldap:// + StartTLS.
AD_SERVER_URI = os.getenv('AD_SERVER_URI', '')
AD_USE_STARTTLS = env_bool('AD_USE_STARTTLS', default=False)
# PEM-файл корпоративного УЦ: им проверяется сертификат контроллера.
AD_CA_CERT_FILE = os.getenv('AD_CA_CERT_FILE', '')
# Отключать проверку сертификата нельзя на production.
AD_TLS_VERIFY = env_bool('AD_TLS_VERIFY', default=True)

# Сервисная учётная запись для поиска сотрудников в каталоге.
AD_BIND_DN = os.getenv('AD_BIND_DN', '')
AD_BIND_PASSWORD = os.getenv('AD_BIND_PASSWORD', '')
AD_USER_SEARCH_BASE = os.getenv('AD_USER_SEARCH_BASE', '')

# Доменная группа, члены которой допускаются на портал.
# Если пусто — допускается любой сотрудник домена.
AD_REQUIRED_GROUP = os.getenv('AD_REQUIRED_GROUP', '')
# Группа Django, в которую попадают JIT-пользователи.
AD_DEFAULT_GROUP = os.getenv(
    'AD_DEFAULT_GROUP',
    'Пользователи портала',
)
# Обновлять ФИО и кадровые поля при каждом входе через AD.
AD_SYNC_ATTRIBUTES = env_bool('AD_SYNC_ATTRIBUTES', default=True)

# Соответствие полей User атрибутам каталога.
# Поле username из AD не заполняется специально: внутренний логин
# портала может отличаться от доменного (см. User.ad_login).
AD_ATTR_MAP = {
    'last_name': 'sn',
    'first_name': 'givenName',
    'middle_name': 'middleName',
    'email': 'mail',
    'position': 'title',
    'department': 'department',
}

# Порядок важен: Django перебирает backend'ы по очереди.
AUTHENTICATION_BACKENDS = ['accounts.backends.PortalBackend']
if AD_ENABLED:
    AUTHENTICATION_BACKENDS.append('accounts.backends.ADBackend')

# Стандартные валидаторы пароля Django.
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': (
            'django.contrib.auth.password_validation.'
            'UserAttributeSimilarityValidator'
        ),
    },
    {
        'NAME': (
            'django.contrib.auth.password_validation.MinimumLengthValidator'
        ),
    },
    {
        'NAME': (
            'django.contrib.auth.password_validation.CommonPasswordValidator'
        ),
    },
    {
        'NAME': (
            'django.contrib.auth.password_validation.NumericPasswordValidator'
        ),
    },
]

# --- Локализация ------------------------------------------------------------

LANGUAGE_CODE = 'ru-ru'
TIME_ZONE = 'Europe/Moscow'
USE_I18N = True
USE_TZ = True

# --- Статика и пользовательские файлы --------------------------------------

STATIC_URL = 'static/'
# Дополнительные каталоги статики проекта (не приложений).
STATICFILES_DIRS = [BASE_DIR / 'static']
# Сюда collectstatic складывает статику для production.
# На сервере путь можно вынести наружу через DJANGO_STATIC_ROOT.
STATIC_ROOT = Path(
    os.getenv('DJANGO_STATIC_ROOT', str(BASE_DIR / 'staticfiles')),
)

STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        # В разработке runserver сам отдаёт статику, поэтому хэш
        # в именах файлов не нужен. В production WhiteNoise сжимает
        # файлы и добавляет хэш в имя (cache busting).
        'BACKEND': (
            'django.contrib.staticfiles.storage.StaticFilesStorage'
            if DEBUG
            else ('whitenoise.storage.CompressedManifestStaticFilesStorage')
        ),
    },
}

# Загруженные редакции документов СМК (PDF, DOCX и т.п.).
# На production каталог должен быть вне web-root nginx: файлы
# отдаёт только RevisionFileView. Путь задаётся DJANGO_MEDIA_ROOT,
# например /var/lib/portal-ksmk/media.
MEDIA_URL = 'media/'
MEDIA_ROOT = Path(
    os.getenv('DJANGO_MEDIA_ROOT', str(BASE_DIR / 'media')),
)

# --- Прочее -----------------------------------------------------------------

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# CSS-класс для сообщений об ошибках (см. шаблон base.html).
MESSAGE_TAGS = {
    message_constants.ERROR: 'danger',
}
