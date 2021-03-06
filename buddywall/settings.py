# -*- coding: utf-8 -*-
from ragendja.settings_pre import *
import os

# Increase this when you update your media on the production site, so users
# don't have to refresh their cache. By setting this your MEDIA_URL
# automatically becomes /media/MEDIA_VERSION/
MEDIA_VERSION = 1

DATABASE_ENGINE = 'appengine'           # 'postgresql_psycopg2', 'postgresql', 'mysql', 'sqlite3' or 'oracle'.
DATABASE_NAME = ''             # Or path to database file if using sqlite3.
DATABASE_USER = ''             # Not used with sqlite3.
DATABASE_PASSWORD = ''         # Not used with sqlite3.
DATABASE_HOST = ''             # Set to empty string for localhost. Not used with sqlite3.
DATABASE_PORT = ''             # Set to empty string for default. Not used with sqlite3.

# Local time zone for this installation. Choices can be found here:
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# although not all choices may be available on all operating systems.
# If running in a Windows environment this must be set to the same as your
# system time zone.
TIME_ZONE = 'Asia/Shanghai'

# Language code for this installation. All choices can be found here:
# http://www.i18nguy.com/unicode/language-identifiers.html
LANGUAGE_CODE = 'en-us'

SITE_ID = 1

# If you set this to False, Django will make some optimizations so as not
# to load the internationalization machinery.
USE_I18N = False

# Absolute path to the directory that holds media.
# Example: "/home/media/media.lawrence.com/"
MEDIA_ROOT = ''

# URL prefix for admin media -- CSS, JavaScript and images. Make sure to use a
# trailing slash.
# Examples: "http://foo.com/media/", "/media/".
ADMIN_MEDIA_PREFIX = '/media/'

# Make this unique, and don't share it with anybody.
SECRET_KEY = 'my_secret_key'

TEMPLATE_CONTEXT_PROCESSORS = (
    'django.core.context_processors.auth',
    'django.core.context_processors.media',
    'django.core.context_processors.request',
    'django.core.context_processors.i18n',
)

MIDDLEWARE_CLASSES = [
    'django.contrib.sessions.middleware.SessionMiddleware',
    # Django authentication
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.http.ConditionalGetMiddleware',
    'django.middleware.gzip.GZipMiddleware',
    'pyxn.djangoxn.XiaoneiMiddleware',
]

ROOT_URLCONF = 'urls'

ROOT_PATH = os.path.dirname(__file__)
import logging
TEMPLATE_DIRS = (
    os.path.join(ROOT_PATH, 'templates')
)

INSTALLED_APPS = (
    'django.contrib.auth',
    'django.contrib.sessions',
    'django.contrib.admin',
    'django.contrib.redirects',
    'django.contrib.sites',
    'appenginepatcher',
    'buddywall',
)

logging.basicConfig(
    level = logging.DEBUG,
    format = '%(asctime)s %(levelname)s %(message)s',
)

#django logging
LOGGING_OUTPUT_ENABLED = True
INTERNAL_IPS = ('127.0.0.1',)

logging.debug('dev mode: %s' % DEBUG)

if DEBUG:
    XIAONEI_API_KEY = 'API_KEY_FOR_DEV'
    XIAONEI_SECRET_KEY = 'API_SECRET_FOR_DEV'
    XIAONEI_APP_NAME = "buddywalldev"
    SERVER_URL = 'http://SERVER_URL_FOR_DEV'
else:
    XIAONEI_API_KEY = 'API_KEY_FOR_PRODUCTION'
    XIAONEI_SECRET_KEY = 'API_SECRET_FOR_PRODUCTION'
    XIAONEI_APP_NAME = "buddywall"
    # URL that handles the media served from MEDIA_ROOT. Make sure to use a
    # trailing slash if there is a path component (optional in other cases).
    # Examples: "http://media.lawrence.com", "http://example.com/media/"
    SERVER_URL = 'http://SERVER_URL_FOR_PRODUCTION'
    
if DEBUG:
    MIDDLEWARE_CLASSES.append('buddywall.ConsoleExceptionMiddleware')
    
TEMPLATE_DEBUG = DEBUG
XIAONEI_CALLBACK_PATH = "/xn/"
XIAONEI_INTERNAL = True

from ragendja.settings_post import *