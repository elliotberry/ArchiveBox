from typing import List, Optional, Dict
from pathlib import Path

from django.apps import AppConfig
from django.core.checks import Tags, Warning, register

from pydantic import (
    Field,
    SerializeAsAny,
)

from pydantic_pkgr import BinProvider, BinName, Binary, EnvProvider, NpmProvider
from pydantic_pkgr.binprovider import bin_abspath
from pydantic_pkgr.binary import BinProviderName, ProviderLookupDict

from plugantic.extractors import Extractor, ExtractorName
from plugantic.plugins import Plugin
from plugantic.configs import ConfigSet, ConfigSectionName

from pkg.settings import env


###################### Config ##########################

class SinglefileToggleConfig(ConfigSet):
    section: ConfigSectionName = 'ARCHIVE_METHOD_TOGGLES'

    SAVE_SINGLEFILE: bool = True


class SinglefileDependencyConfig(ConfigSet):
    section: ConfigSectionName = 'DEPENDENCY_CONFIG'

    SINGLEFILE_BINARY: str = Field(default='wget')
    SINGLEFILE_ARGS: Optional[List[str]] = Field(default=None)
    SINGLEFILE_EXTRA_ARGS: List[str] = []
    SINGLEFILE_DEFAULT_ARGS: List[str] = ['--timeout={TIMEOUT-10}']

class SinglefileOptionsConfig(ConfigSet):
    section: ConfigSectionName = 'ARCHIVE_METHOD_OPTIONS'

    # loaded from shared config
    SINGLEFILE_USER_AGENT: str = Field(default='', alias='USER_AGENT')
    SINGLEFILE_TIMEOUT: int = Field(default=60, alias='TIMEOUT')
    SINGLEFILE_CHECK_SSL_VALIDITY: bool = Field(default=True, alias='CHECK_SSL_VALIDITY')
    SINGLEFILE_RESTRICT_FILE_NAMES: str = Field(default='windows', alias='RESTRICT_FILE_NAMES')
    SINGLEFILE_COOKIES_FILE: Optional[Path] = Field(default=None, alias='COOKIES_FILE')



DEFAULT_CONFIG = {
    'CHECK_SSL_VALIDITY': False,
    'SAVE_SINGLEFILE': True,
    'TIMEOUT': 120,
}

PLUGIN_CONFIG = [
    SinglefileToggleConfig(**DEFAULT_CONFIG),
    SinglefileDependencyConfig(**DEFAULT_CONFIG),
    SinglefileOptionsConfig(**DEFAULT_CONFIG),
]

###################### Binaries ############################

min_version: str = "1.1.54"
max_version: str = "2.0.0"

class SinglefileBinary(Binary):
    name: BinName = 'single-file'
    providers_supported: List[BinProvider] = [NpmProvider()]


    provider_overrides: Dict[BinProviderName, ProviderLookupDict] ={
        'env': {
            'abspath': lambda: bin_abspath('single-file-node.js', PATH=env.PATH) or bin_abspath('single-file', PATH=env.PATH),
        },
        'npm': {
            # 'abspath': lambda: bin_abspath('single-file', PATH=NpmProvider().PATH) or bin_abspath('single-file', PATH=env.PATH),
            'subdeps': lambda: f'single-file-cli@>={min_version} <{max_version}',
        },
    }


###################### Extractors ##########################

class SinglefileExtractor(Extractor):
    name: ExtractorName = 'singlefile'
    binary: Binary = SinglefileBinary()

    def get_output_path(self, snapshot) -> Path:
        return Path(snapshot.link_dir) / 'singlefile.html'


###################### Plugins #############################


class SinglefilePlugin(Plugin):
    name: str = 'singlefile'
    configs: List[SerializeAsAny[ConfigSet]] = [*PLUGIN_CONFIG]
    binaries: List[SerializeAsAny[Binary]] = [SinglefileBinary()]
    extractors: List[SerializeAsAny[Extractor]] = [SinglefileExtractor()]

PLUGINS = [SinglefilePlugin()]

###################### Django Apps #########################

class SinglefileConfig(AppConfig):
    name = 'builtin_plugins.singlefile'
    verbose_name = 'SingleFile'

    def ready(self):
        pass
        # print('Loaded singlefile plugin')
