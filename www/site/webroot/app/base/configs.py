# -*- coding: utf-8 -*-

import configparser
import os
import json

from .logger import log
from .utils import AttrDict, tp_convert_to_attr_dict, tp_make_dir

__all__ = ['tp_cfg']


class BaseAppConfig(dict):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        import builtins
        if '__app_cfg__' in builtins.__dict__:
            raise RuntimeError('AppConfig instance already exists.')

        self['_cfg_default'] = {}
        self['_cfg_loaded'] = {}
        self['_kvs'] = {'_': AttrDict()}
        self['_cfg_file'] = ''

        self._on_init()

    def __getattr__(self, name):
        _name = name.replace('-', '_')
        if _name in self['_kvs']:
            return self['_kvs'][_name]
        else:
            if _name in self['_kvs']['_']:
                return self['_kvs']['_'][_name]
            else:
                return AttrDict()

    def __setattr__(self, key, val):
        x = key.split('::')
        if 1 == len(x):
            _sec = '_'
            _key = x[0].replace('-', '_')
        elif 2 == len(x):
            _sec = x[0].replace('-', '_')
            _key = x[1].replace('-', '_')
        else:
            raise RuntimeError('invalid name.')

        if _sec not in self['_kvs']:
            self['_kvs'][_sec] = {}
        self['_kvs'][_sec][_key] = val

    def _on_init(self):
        raise RuntimeError('can not create instance for base class.')

    def _on_get_save_info(self):
        raise RuntimeError('can not create instance for base class.')

    def _on_load(self, cfg_parser):
        raise RuntimeError('can not create instance for base class.')

    def reload(self):
        self['_cfg_default'] = {}
        self['_cfg_loaded'] = {}
        self['_kvs'] = {'_': self['_kvs']['_']}
        self._on_init()
        return self.load(self['_cfg_file'])

    def set_kv(self, key, val):
        x = key.split('::')
        if 1 == len(x):
            _sec = '_'
            _key = x[0].replace('-', '_')
        elif 2 == len(x):
            _sec = x[0].replace('-', '_')
            _key = x[1].replace('-', '_')
        else:
            raise RuntimeError('invalid name.')

        if _sec not in self['_cfg_loaded']:
            self['_cfg_loaded'][_sec] = {}
        self['_cfg_loaded'][_sec][_key] = val
        self._update_kvs(_sec, _key, val)

    def set_default(self, key, val, comment=None):
        x = key.split('::')
        if 1 == len(x):
            _sec = '_'
            _key = x[0].replace('-', '_')
        elif 2 == len(x):
            _sec = x[0].replace('-', '_')
            _key = x[1].replace('-', '_')
        else:
            raise RuntimeError('invalid name.')

        if _sec not in self['_cfg_default']:
            self['_cfg_default'][_sec] = {}
        if _key not in self['_cfg_default'][_sec]:
            self['_cfg_default'][_sec][_key] = {}
            self['_cfg_default'][_sec][_key]['value'] = val
            self['_cfg_default'][_sec][_key]['comment'] = comment
        else:
            self['_cfg_default'][_sec][_key]['value'] = val

            if comment is not None:
                self['_cfg_default'][_sec][_key]['comment'] = comment
            elif 'comment' not in self['_cfg_default'][_sec][_key]:
                self['_cfg_default'][_sec][_key]['comment'] = None

        self._update_kvs(_sec, _key, val)

    def load(self, cfg_file):
        if not os.path.exists(cfg_file):
            log.e('configuration file does not exists: [{}]\n'.format(cfg_file))
            return False
        try:
            _cfg = configparser.ConfigParser()
            _cfg.read(cfg_file)
        except:
            log.e('can not load configuration file: [{}]\n'.format(cfg_file))
            return False

        if not self._on_load(_cfg):
            return False

        self['_cfg_file'] = cfg_file
        return True

    def save(self, cfg_file=None):
        if cfg_file is None:
            cfg_file = self['_cfg_file']
        _save = self._on_get_save_info()

        cnt = ['; codec: utf-8\n']

        is_first_section = True
        for sections in _save:
            for sec_name in sections:
                sec_name = sec_name.replace('-', '_')
                if sec_name in self['_cfg_default'] or sec_name in self['_cfg_loaded']:
                    if not is_first_section:
                        cnt.append('\n')
                    cnt.append('[{}]'.format(sec_name))
                    is_first_section = False
                for k in sections[sec_name]:
                    _k = k.replace('-', '_')
                    have_comment = False
                    if sec_name in self['_cfg_default'] and _k in self['_cfg_default'][sec_name] and 'comment' in self['_cfg_default'][sec_name][_k]:
                        comments = self['_cfg_default'][sec_name][_k]['comment']
                        if comments is not None:
                            comments = self['_cfg_default'][sec_name][_k]['comment'].split('\n')
                            cnt.append('')
                            have_comment = True
                            for comment in comments:
                                cnt.append('; {}'.format(comment))

                    if sec_name in self['_cfg_loaded'] and _k in self['_cfg_loaded'][sec_name]:
                        if not have_comment:
                            cnt.append('')
                        cnt.append('{}={}'.format(k, self['_cfg_loaded'][sec_name][_k]))

        cnt.append('\n')
        tmp_file = '{}.tmp'.format(cfg_file)

        try:
            with open(tmp_file, 'w', encoding='utf8') as f:
                f.write('\n'.join(cnt))
            if os.path.exists(cfg_file):
                os.unlink(cfg_file)
            os.rename(tmp_file, cfg_file)
            return True
        except Exception as e:
            print(e.__str__())
            return False

    def _update_kvs(self, section, key, val):
        if section not in self['_kvs']:
            self['_kvs'][section] = AttrDict()
        self['_kvs'][section][key] = val

    def get_str(self, key, def_value=None):
        x = key.split('::')
        if 1 == len(x):
            _sec = '_'
            _key = x[0].replace('-', '_')
        elif 2 == len(x):
            _sec = x[0].replace('-', '_')
            _key = x[1].replace('-', '_')
        else:
            return def_value, False

        if _sec not in self['_kvs']:
            return def_value, False
        if _key not in self['_kvs'][_sec]:
            return def_value, False

        if self['_kvs'][_sec][_key] is None:
            return def_value, False

        return str(self['_kvs'][_sec][_key]), True

    def get_int(self, key, def_value=-1):
        x = key.split('::')
        if 1 == len(x):
            _sec = '_'
            _key = x[0].replace('-', '_')
        elif 2 == len(x):
            _sec = x[0].replace('-', '_')
            _key = x[1].replace('-', '_')
        else:
            return def_value, False

        if _sec not in self['_kvs']:
            return def_value, False
        if _key not in self['_kvs'][_sec]:
            return def_value, False

        if self['_kvs'][_sec][_key] is None:
            return def_value, False

        try:
            return int(self['_kvs'][_sec][_key]), True
        except ValueError as e:
            print(e.__str__())
            return def_value, False

    def get_bool(self, key, def_value=False):
        x = key.split('::')
        if 1 == len(x):
            _sec = '_'
            _key = x[0].replace('-', '_')
        elif 2 == len(x):
            _sec = x[0].replace('-', '_')
            _key = x[1].replace('-', '_')
        else:
            return def_value, False

        if _sec not in self['_kvs']:
            return def_value, False
        if _key not in self['_kvs'][_sec]:
            return def_value, False

        if self['_kvs'][_sec][_key] is None:
            return def_value, False

        tmp = str(self['_kvs'][_sec][_key]).lower()

        if tmp in ['yes', 'true', '1']:
            return True, True
        elif tmp in ['no', 'false', '0']:
            return False, True
        else:
            return def_value, False


class AppConfig(BaseAppConfig):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def _on_init(self):
        self.set_default('common::ip', '0.0.0.0', 'ip=0.0.0.0')
        self.set_default('common::port', 7218,
                         'port listen by web server, default to 7218.\n'
                         'DO NOT FORGET update common::web-server-rpc in base.ini if you modified this setting.\n'
                         'port=7218')
        self.set_default('common::log-file', None,
                         'log file of web server, default to /var/log/tp4a.com/www.log\n'
                         'log-file=/var/log/tp4a.com/www.log'
                         )
        self.set_default('common::log-level', 2,
                         '`log-level` can be 0 ~ 4, default to 2.\n'
                         'LOG_LEVEL_DEBUG     0   log every-thing.\n'
                         'LOG_LEVEL_VERBOSE   1   log every-thing but without debug message.\n'
                         'LOG_LEVEL_INFO      2   log information/warning/error message.\n'
                         'LOG_LEVEL_WARN      3   log warning and error message.\n'
                         'LOG_LEVEL_ERROR     4   log error message only.\n'
                         'log-level=2'
                         )
        self.set_default('common::debug-mode', 0,
                         '0/1. default to 0.\n'
                         'in debug mode, `log-level` force to 0 and trace call stack when exception raised.\n'
                         'debug-mode=0'
                         )
        self.set_default('database::type', 'sqlite',
                         'database in use, should be sqlite/mysql, default to sqlite.\n'
                         'type=sqlite'
                         )
        self.set_default('database::sqlite-file', None,
                         'sqlite-file=/var/lib/tp4a/data/www.db'
                         )
        self.set_default('database::mysql-host', '127.0.0.1', 'mysql-host=127.0.0.1')
        self.set_default('database::mysql-port', 3306, 'mysql-port=3306')
        self.set_default('database::mysql-db', 'tp4a', 'mysql-db=tp4a')
        self.set_default('database::mysql-prefix', 'tp4a_', 'mysql-prefix=tp4a_')
        self.set_default('database::mysql-user', 'tp4a', 'mysql-user=tp4a')
        self.set_default('database::mysql-password', 'password', 'mysql-password=password')

    def _on_get_save_info(self):
        return [
            {'common': ['ip', 'port', 'log-file', 'log-level', 'debug-mode']},
            {'database': ['type', 'sqlite-file', 'mysql-host', 'mysql-port', 'mysql-db', 'mysql-prefix', 'mysql-user', 'mysql-password']}
        ]

    def _on_load(self, cfg_parser):
        if 'common' not in cfg_parser:
            log.e('invalid config file, need `common` section.\n')
            return False
        if 'database' not in cfg_parser:
            log.e('invalid config file, need `database` section.\n')
            return False

        _sec = cfg_parser['common']

        _tmp_int = _sec.getint('log-level', -1)
        if log.LOG_DEBUG <= _tmp_int <= log.LOG_ERROR:
            self.set_kv('common::log-level', _tmp_int)
        log.set_attribute(min_level=self.common.log_level)

        _tmp_bool = _sec.getint('debug-mode', False)
        self.set_kv('common::debug-mode', _tmp_bool)
        if _tmp_bool:
            log.set_attribute(min_level=log.LOG_DEBUG, trace_error=log.TRACE_ERROR_FULL)

        _tmp_str = _sec.get('ip', None)
        if _tmp_str is not None:
            self.set_kv('common::ip', _tmp_str)

        _tmp_int = _sec.getint('port', -1)
        if -1 != _tmp_int:
            self.set_kv('common::port', _tmp_int)

        _tmp_str = _sec.get('log-file', None)
        if _tmp_str is not None:
            self.set_kv('common::log-file', _tmp_str)

        _sec = cfg_parser['database']

        _tmp_str = _sec.get('type', None)
        if _tmp_str is not None:
            self.set_kv('database::type', _tmp_str)

        _tmp_str = _sec.get('sqlite-file', None)
        if _tmp_str is not None:
            self.set_kv('database::sqlite-file', _tmp_str)

        _tmp_str = _sec.get('mysql-host', None)
        if _tmp_str is not None:
            self.set_kv('database::mysql-host', _tmp_str)

        _tmp_int = _sec.getint('mysql-port', -1)
        if _tmp_int != -1:
            self.set_kv('database::mysql-port', _tmp_int)

        _tmp_str = _sec.get('mysql-db', None)
        if _tmp_str is not None:
            self.set_kv('database::mysql-db', _tmp_str)

        _tmp_str = _sec.get('mysql-prefix', None)
        if _tmp_str is not None:
            self.set_kv('database::mysql-prefix', _tmp_str)

        _tmp_str = _sec.get('mysql-user', None)
        if _tmp_str is not None:
            self.set_kv('database::mysql-user', _tmp_str)

        _tmp_str = _sec.get('mysql-password', None)
        if _tmp_str is not None:
            self.set_kv('database::mysql-password', _tmp_str)

        _log_file, ok = self.get_str('common::log-file')
        if ok and _log_file:
            self.log_path = os.path.abspath(os.path.dirname(_log_file))
        else:
            _log_file = os.path.join(self.log_path, 'tpweb.log')
            self.set_default('common::log-file', _log_file)

        if not os.path.exists(self.log_path):
            tp_make_dir(self.log_path)
            if not os.path.exists(self.log_path):
                log.e('Can not create log path:{}\n'.format(self.log_path))
                return False

        log.set_attribute(filename=_log_file)

        return True


def tp_cfg():
    """
    :rtype: app.base.configs.AppConfig
    """
    import builtins
    if '__app_cfg__' not in builtins.__dict__:
        builtins.__dict__['__app_cfg__'] = AppConfig()
    return builtins.__dict__['__app_cfg__']
