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
                # В Docker-контейнере используется самоподписанный
                # сертификат, поэтому его проверку отключаем.
                'extra_params': 'TrustServerCertificate=yes',
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

# Сейчас поддерживается только вход по учётной записи портала.
# Позже рядом появится backend для Active Directory.
AUTHENTICATION_BACKENDS = ['accounts.backends.PortalBackend']

LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/documents/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

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
STATIC_ROOT = BASE_DIR / 'staticfiles'

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
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

# --- Прочее -----------------------------------------------------------------

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# CSS-класс для сообщений об ошибках (см. шаблон base.html).
MESSAGE_TAGS = {
    message_constants.ERROR: 'danger',
}
