__package__ = 'archivebox.core'

import os
import sys
import re
import logging
import inspect
import tempfile
from typing import Any, Dict

from pathlib import Path
from django.utils.crypto import get_random_string

from ..config import CONFIG
from ..config_stubs import AttrDict
assert isinstance(CONFIG, AttrDict)

IS_MIGRATING = 'makemigrations' in sys.argv[:3] or 'migrate' in sys.argv[:3]
IS_TESTING = 'test' in sys.argv[:3] or 'PYTEST_CURRENT_TEST' in os.environ
IS_SHELL = 'shell' in sys.argv[:3] or 'shell_plus' in sys.argv[:3]

################################################################################
### Django Core Settings
################################################################################

WSGI_APPLICATION = 'core.wsgi.application'
ROOT_URLCONF = 'core.urls'

LOGIN_URL = '/accounts/login/'
LOGOUT_REDIRECT_URL = os.environ.get('LOGOUT_REDIRECT_URL', '/')

PASSWORD_RESET_URL = '/accounts/password_reset/'
APPEND_SLASH = True

DEBUG = CONFIG.DEBUG or ('--debug' in sys.argv)


BUILTIN_PLUGINS_DIR = CONFIG.PACKAGE_DIR / 'builtin_plugins'
USER_PLUGINS_DIR = CONFIG.OUTPUT_DIR / 'user_plugins'

def find_plugins(plugins_dir, prefix: str) -> Dict[str, Any]:
    plugins = {
        f'{prefix}.{plugin_entrypoint.parent.name}': plugin_entrypoint.parent
        for plugin_entrypoint in plugins_dir.glob('*/apps.py')
    }
    # print(f'Found {prefix} plugins:\n', '\n    '.join(plugins.keys()))
    return plugins

INSTALLED_PLUGINS = {
    **find_plugins(BUILTIN_PLUGINS_DIR, prefix='builtin_plugins'),
    **find_plugins(USER_PLUGINS_DIR, prefix='user_plugins'),
}


INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.admin',
    'django_jsonform',
    
    'signal_webhooks',
    'abid_utils',
    'plugantic',
    'core',
    'api',
    'pkg',

    *INSTALLED_PLUGINS.keys(),

    'admin_data_views',
    'django_extensions',
]


# For usage with https://www.jetadmin.io/integrations/django
# INSTALLED_APPS += ['jet_django']
# JET_PROJECT = 'archivebox'
# JET_TOKEN = 'some-api-token-here'


MIDDLEWARE = [
    'core.middleware.TimezoneMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'core.middleware.ReverseProxyAuthMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'core.middleware.CacheControlMiddleware',
]

################################################################################
### Authentication Settings
################################################################################

# AUTH_USER_MODEL = 'auth.User'   # cannot be easily changed unfortunately

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.RemoteUserBackend',
    'django.contrib.auth.backends.ModelBackend',
]

if CONFIG.LDAP:
    try:
        import ldap
        from django_auth_ldap.config import LDAPSearch

        global AUTH_LDAP_SERVER_URI
        global AUTH_LDAP_BIND_DN
        global AUTH_LDAP_BIND_PASSWORD
        global AUTH_LDAP_USER_SEARCH
        global AUTH_LDAP_USER_ATTR_MAP

        AUTH_LDAP_SERVER_URI = CONFIG.LDAP_SERVER_URI
        AUTH_LDAP_BIND_DN = CONFIG.LDAP_BIND_DN
        AUTH_LDAP_BIND_PASSWORD = CONFIG.LDAP_BIND_PASSWORD

        assert AUTH_LDAP_SERVER_URI and CONFIG.LDAP_USERNAME_ATTR and CONFIG.LDAP_USER_FILTER, 'LDAP_* config options must all be set if LDAP=True'

        AUTH_LDAP_USER_SEARCH = LDAPSearch(
            CONFIG.LDAP_USER_BASE,
            ldap.SCOPE_SUBTREE,
            '(&(' + CONFIG.LDAP_USERNAME_ATTR + '=%(user)s)' + CONFIG.LDAP_USER_FILTER + ')',
        )

        AUTH_LDAP_USER_ATTR_MAP = {
            'username': CONFIG.LDAP_USERNAME_ATTR,
            'first_name': CONFIG.LDAP_FIRSTNAME_ATTR,
            'last_name': CONFIG.LDAP_LASTNAME_ATTR,
            'email': CONFIG.LDAP_EMAIL_ATTR,
        }

        AUTHENTICATION_BACKENDS = [
            'django.contrib.auth.backends.ModelBackend',
            'django_auth_ldap.backend.LDAPBackend',
        ]
    except ModuleNotFoundError:
        sys.stderr.write('[X] Error: Found LDAP=True config but LDAP packages not installed. You may need to run: pip install archivebox[ldap]\n\n')
        # dont hard exit here. in case the user is just running "archivebox version" or "archivebox help", we still want those to work despite broken ldap
        # sys.exit(1)



################################################################################
### Staticfile and Template Settings
################################################################################

STATIC_URL = '/static/'

STATICFILES_DIRS = [
    *([str(CONFIG.CUSTOM_TEMPLATES_DIR / 'static')] if CONFIG.CUSTOM_TEMPLATES_DIR else []),
    str(Path(CONFIG.PACKAGE_DIR) / CONFIG.TEMPLATES_DIR_NAME / 'static'),
]

TEMPLATE_DIRS = [
    *([str(CONFIG.CUSTOM_TEMPLATES_DIR)] if CONFIG.CUSTOM_TEMPLATES_DIR else []),
    str(Path(CONFIG.PACKAGE_DIR) / CONFIG.TEMPLATES_DIR_NAME / 'core'),
    str(Path(CONFIG.PACKAGE_DIR) / CONFIG.TEMPLATES_DIR_NAME / 'admin'),
    str(Path(CONFIG.PACKAGE_DIR) / CONFIG.TEMPLATES_DIR_NAME),
]

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': TEMPLATE_DIRS,
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]


################################################################################
### External Service Settings
################################################################################


CACHE_DB_FILENAME = 'cache.sqlite3'
CACHE_DB_PATH = CONFIG.CACHE_DIR / CACHE_DB_FILENAME
CACHE_DB_TABLE = 'django_cache'

DATABASE_FILE = Path(CONFIG.OUTPUT_DIR) / CONFIG.SQL_INDEX_FILENAME
DATABASE_NAME = os.environ.get("ARCHIVEBOX_DATABASE_NAME", str(DATABASE_FILE))

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': DATABASE_NAME,
        'OPTIONS': {
            'timeout': 60,
            'check_same_thread': False,
        },
        'TIME_ZONE': CONFIG.TIMEZONE,
        # DB setup is sometimes modified at runtime by setup_django() in config.py
    },
    # 'cache': {
    #     'ENGINE': 'django.db.backends.sqlite3',
    #     'NAME': CACHE_DB_PATH,
    #     'OPTIONS': {
    #         'timeout': 60,
    #         'check_same_thread': False,
    #     },
    #     'TIME_ZONE': CONFIG.TIMEZONE,
    # },
}
MIGRATION_MODULES = {'signal_webhooks': None}

# as much as I'd love this to be a UUID or ULID field, it's not supported yet as of Django 5.0
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


CACHES = {
    'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'},
    # 'sqlite': {'BACKEND': 'django.core.cache.backends.db.DatabaseCache', 'LOCATION': 'cache'},
    # 'dummy': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'},
    # 'filebased': {"BACKEND": "django.core.cache.backends.filebased.FileBasedCache", "LOCATION": CACHE_DIR / 'cache_filebased'},
}

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'


STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
    "archive": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": {
            "base_url": "/archive/",
            "location": CONFIG.ARCHIVE_DIR,
        },
    },
    # "personas": {
    #     "BACKEND": "django.core.files.storage.FileSystemStorage",
    #     "OPTIONS": {
    #         "base_url": "/personas/",
    #         "location": PERSONAS_DIR,
    #     },
    # },
}

################################################################################
### Security Settings
################################################################################

SECRET_KEY = CONFIG.SECRET_KEY or get_random_string(50, 'abcdefghijklmnopqrstuvwxyz0123456789_')

ALLOWED_HOSTS = CONFIG.ALLOWED_HOSTS.split(',')
CSRF_TRUSTED_ORIGINS = list(set(CONFIG.CSRF_TRUSTED_ORIGINS.split(',')))

# automatically fix case when user sets ALLOWED_HOSTS (e.g. to archivebox.example.com)
# but forgets to add https://archivebox.example.com to CSRF_TRUSTED_ORIGINS
for hostname in ALLOWED_HOSTS:
    https_endpoint = f'https://{hostname}'
    if hostname != '*' and https_endpoint not in CSRF_TRUSTED_ORIGINS:
        print(f'[!] WARNING: {https_endpoint} from ALLOWED_HOSTS should be added to CSRF_TRUSTED_ORIGINS')
        CSRF_TRUSTED_ORIGINS.append(https_endpoint)

SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'

CSRF_COOKIE_SECURE = False
SESSION_COOKIE_SECURE = False
SESSION_COOKIE_DOMAIN = None
SESSION_COOKIE_AGE = 1209600  # 2 weeks
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_SAVE_EVERY_REQUEST = True

SESSION_ENGINE = "django.contrib.sessions.backends.db"

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

DATA_UPLOAD_MAX_NUMBER_FIELDS = None

################################################################################
### Shell Settings
################################################################################

SHELL_PLUS = 'ipython'
SHELL_PLUS_PRINT_SQL = False
IPYTHON_ARGUMENTS = ['--no-confirm-exit', '--no-banner']
IPYTHON_KERNEL_DISPLAY_NAME = 'ArchiveBox Django Shell'
if IS_SHELL:
    os.environ['PYTHONSTARTUP'] = str(Path(CONFIG.PACKAGE_DIR) / 'core' / 'welcome_message.py')


################################################################################
### Internationalization & Localization Settings
################################################################################

LANGUAGE_CODE = 'en-us'
USE_I18N = True
USE_TZ = True
DATETIME_FORMAT = 'Y-m-d g:iA'
SHORT_DATETIME_FORMAT = 'Y-m-d h:iA'
TIME_ZONE = CONFIG.TIMEZONE        # django convention is TIME_ZONE, archivebox config uses TIMEZONE, they are equivalent


from django.conf.locale.en import formats as en_formats    # type: ignore

en_formats.DATETIME_FORMAT = DATETIME_FORMAT
en_formats.SHORT_DATETIME_FORMAT = SHORT_DATETIME_FORMAT


################################################################################
### Logging Settings
################################################################################

IGNORABLE_404_URLS = [
    re.compile(r'apple-touch-icon.*\.png$'),
    re.compile(r'favicon\.ico$'),
    re.compile(r'robots\.txt$'),
    re.compile(r'.*\.(css|js)\.map$'),
]
IGNORABLE_200_URLS = [
    re.compile(r'^"GET /static/.* HTTP/.*" (200|30.) .+', re.I | re.M),
    re.compile(r'^"GET /admin/jsi18n/ HTTP/.*" (200|30.) .+', re.I | re.M),
]

class NoisyRequestsFilter(logging.Filter):
    def filter(self, record) -> bool:
        logline = record.getMessage()

        # ignore harmless 404s for the patterns in IGNORABLE_404_URLS
        for ignorable_url_pattern in IGNORABLE_404_URLS:
            ignorable_log_pattern = re.compile(f'^"GET /.*/?{ignorable_url_pattern.pattern[:-1]} HTTP/.*" (200|30.|404) .+$', re.I | re.M)
            if ignorable_log_pattern.match(logline):
                return False

            ignorable_log_pattern = re.compile(f'^Not Found: /.*/?{ignorable_url_pattern.pattern}', re.I | re.M)
            if ignorable_log_pattern.match(logline):
                return False

        # ignore staticfile requests that 200 or 30*
        for ignorable_url_pattern in IGNORABLE_200_URLS:
            if ignorable_log_pattern.match(logline):
                return False
            
        return True


ERROR_LOG = tempfile.NamedTemporaryFile().name

if CONFIG.LOGS_DIR.exists():
    ERROR_LOG = (CONFIG.LOGS_DIR / 'errors.log')
else:
    # historically too many edge cases here around creating log dir w/ correct permissions early on
    # if there's an issue on startup, we trash the log and let user figure it out via stdout/stderr
    print(f'[!] WARNING: data/logs dir does not exist. Logging to temp file: {ERROR_LOG}')

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
        'logfile': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': ERROR_LOG,
            'maxBytes': 1024 * 1024 * 25,  # 25 MB
            'backupCount': 10,
        },
    },
    'filters': {
        'noisyrequestsfilter': {
            '()': NoisyRequestsFilter,
        }
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'logfile'],
            'level': 'INFO',
            'filters': ['noisyrequestsfilter'],
        },
        'django.server': {
            'handlers': ['console', 'logfile'],
            'level': 'INFO',
            'filters': ['noisyrequestsfilter'],
        }
    },
}


################################################################################
### REST API Outbound Webhooks settings
################################################################################

# Add default webhook configuration to the User model
SIGNAL_WEBHOOKS_CUSTOM_MODEL = 'api.models.OutboundWebhook'
SIGNAL_WEBHOOKS = {
    "HOOKS": {
        # ... is a special sigil value that means "use the default autogenerated hooks"
        "django.contrib.auth.models.User": ...,
        "core.models.Snapshot": ...,
        "core.models.ArchiveResult": ...,
        "core.models.Tag": ...,
        "api.models.APIToken": ...,
    },
}

################################################################################
### Admin Data View Settings
################################################################################

ADMIN_DATA_VIEWS = {
    "NAME": "Environment",
    "URLS": [
        {
            "route": "config/",
            "view": "core.views.live_config_list_view",
            "name": "Configuration",
            "items": {
                "route": "<str:key>/",
                "view": "core.views.live_config_value_view",
                "name": "config_val",
            },
        },
        {
            "route": "binaries/",
            "view": "plugantic.views.binaries_list_view",
            "name": "Binaries",
            "items": {
                "route": "<str:key>/",
                "view": "plugantic.views.binary_detail_view",
                "name": "binary",
            },
        },
        {
            "route": "plugins/",
            "view": "plugantic.views.plugins_list_view",
            "name": "Plugins",
            "items": {
                "route": "<str:key>/",
                "view": "plugantic.views.plugin_detail_view",
                "name": "plugin",
            },
        },
    ],
}


################################################################################
### Debug Settings
################################################################################

# only enable debug toolbar when in DEBUG mode with --nothreading (it doesnt work in multithreaded mode)
DEBUG_TOOLBAR = False
DEBUG_TOOLBAR = DEBUG_TOOLBAR and DEBUG and ('--nothreading' in sys.argv) and ('--reload' not in sys.argv)
if DEBUG_TOOLBAR:
    try:
        import debug_toolbar   # noqa
        DEBUG_TOOLBAR = True
    except ImportError:
        DEBUG_TOOLBAR = False

if DEBUG_TOOLBAR:
    INSTALLED_APPS = [*INSTALLED_APPS, 'debug_toolbar']
    INTERNAL_IPS = ['0.0.0.0', '127.0.0.1', '*']
    DEBUG_TOOLBAR_CONFIG = {
        "SHOW_TOOLBAR_CALLBACK": lambda request: True,
        "RENDER_PANELS": True,
    }
    DEBUG_TOOLBAR_PANELS = [
        'debug_toolbar.panels.history.HistoryPanel',
        'debug_toolbar.panels.versions.VersionsPanel',
        'debug_toolbar.panels.timer.TimerPanel',
        'debug_toolbar.panels.settings.SettingsPanel',
        'debug_toolbar.panels.headers.HeadersPanel',
        'debug_toolbar.panels.request.RequestPanel',
        'debug_toolbar.panels.sql.SQLPanel',
        'debug_toolbar.panels.staticfiles.StaticFilesPanel',
        # 'debug_toolbar.panels.templates.TemplatesPanel',
        'debug_toolbar.panels.cache.CachePanel',
        'debug_toolbar.panels.signals.SignalsPanel',
        'debug_toolbar.panels.logging.LoggingPanel',
        'debug_toolbar.panels.redirects.RedirectsPanel',
        'debug_toolbar.panels.profiling.ProfilingPanel',
        'djdt_flamegraph.FlamegraphPanel',
    ]
    MIDDLEWARE = [*MIDDLEWARE, 'debug_toolbar.middleware.DebugToolbarMiddleware']

if DEBUG:
    from django_autotyping.typing import AutotypingSettingsDict

    INSTALLED_APPS += ['django_autotyping']
    AUTOTYPING: AutotypingSettingsDict = {
        "STUBS_GENERATION": {
            "LOCAL_STUBS_DIR": Path(CONFIG.PACKAGE_DIR) / "typings",
        }
    }

# https://github.com/bensi94/Django-Requests-Tracker (improved version of django-debug-toolbar)
# Must delete archivebox/templates/admin to use because it relies on some things we override
# visit /__requests_tracker__/ to access
DEBUG_REQUESTS_TRACKER = True
DEBUG_REQUESTS_TRACKER = DEBUG_REQUESTS_TRACKER and DEBUG
if DEBUG_REQUESTS_TRACKER:
    import requests_tracker

    INSTALLED_APPS += ["requests_tracker"]
    MIDDLEWARE += ["requests_tracker.middleware.requests_tracker_middleware"]
    INTERNAL_IPS = ["127.0.0.1", "10.0.2.2", "0.0.0.0", "*"]

    TEMPLATE_DIRS.insert(0, str(Path(inspect.getfile(requests_tracker)).parent / "templates"))

    REQUESTS_TRACKER_CONFIG = {
        "TRACK_SQL": True,
        "ENABLE_STACKTRACES": False,
        "IGNORE_PATHS_PATTERNS": (
            r".*/favicon\.ico",
            r".*\.png",
            r"/admin/jsi18n/",
        ),
        "IGNORE_SQL_PATTERNS": (
            r"^SELECT .* FROM django_migrations WHERE app = 'requests_tracker'",
            r"^SELECT .* FROM django_migrations WHERE app = 'auth'",
        ),
    }

# https://docs.pydantic.dev/logfire/integrations/django/ (similar to DataDog / NewRelic / etc.)
DEBUG_LOGFIRE = False
DEBUG_LOGFIRE = DEBUG_LOGFIRE and (Path(CONFIG.OUTPUT_DIR) / '.logfire').is_dir()
