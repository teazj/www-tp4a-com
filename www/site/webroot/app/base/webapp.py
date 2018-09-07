# -*- coding: utf-8 -*-

import json
import os
import time
import urllib.parse
import urllib.request

import tornado.httpserver
import tornado.ioloop
import tornado.netutil
import tornado.process
import tornado.web
from app.const import *
from app.base.configs import tp_cfg
from app.base.db import get_db
from app.base.logger import log
from app.base.session import tp_session


class WebApp:
    def __init__(self):
        import builtins
        if '__web_app__' in builtins.__dict__:
            raise RuntimeError('WebApp object exists, you can not create more than one instance.')
        self._cfg_file = ''

    def init(self, path_app_root, path_data):
        log.initialize()

        cfg = tp_cfg()
        cfg.app_path = path_app_root
        cfg.static_path = os.path.join(path_app_root, 'static')
        cfg.template_path = os.path.join(path_app_root, 'view')
        cfg.res_path = os.path.join(path_app_root, 'res')

        cfg.data_path = path_data
        cfg.cfg_path = os.path.join(path_data, 'etc')
        cfg.log_path = os.path.join(path_data, 'log')

        self._cfg_file = os.path.join(cfg.cfg_path, 'web.ini')
        if not cfg.load(self._cfg_file):
            return False

        return True

    def run(self):
        log.i('\n')
        log.i('###############################################################\n')
        log.i('Load config file: {}\n'.format(self._cfg_file))
        log.i('Teleport Web Server starting ...\n')

        # 尝试通过CORE-JSON-RPC获取core服务的配置（主要是ssh/rdp/telnet的端口以及录像文件存放路径）
        # self._get_core_server_config()

        _db = get_db()
        if not _db.init():
            log.e('can not initialize database interface.\n')
            return 0

        _db.connect()
        while not _db.connected:
            log.w('database not connected, retry after 5 seconds.\n')
            time.sleep(5)
            _db.connect()

        cfg = tp_cfg()

        _db.check_status()
        if _db.need_create or _db.need_upgrade:
            cfg.app_mode = APP_MODE_MAINTENANCE
        else:
            cfg.app_mode = APP_MODE_NORMAL

        if not tp_session().init():
            log.e('can not initialize session manager.\n')
            return 0
        # if not tp_stats().init():
        #     log.e('can not initialize system status collector.\n')
        #     return 0

        settings = {
            #
            'cookie_secret': '8946svdABGD345fg98uhIaefEBePIfegOIakjFH43oETzK',

            'login_url': '/auth/login',

            # 指定静态文件的路径，页面模板中可以用 {{ static_url('css/main.css') }} 的方式调用
            'static_path': cfg.static_path,

            # 指定模板文件的路径
            'template_path': cfg.template_path,

            # 防止跨站伪造请求，参见 http://old.sebug.net/paper/books/tornado/#_7
            'xsrf_cookies': False,

            'autoescape': 'xhtml_escape',

            # 'ui_modules': ui_modules,
            'debug': False,

            # 不开启模板和静态文件的缓存，这样一旦模板文件和静态文件变化，刷新浏览器即可看到更新。
            'compiled_template_cache': False,
            'static_hash_cache': False,
        }

        from app.controller import controllers
        _app = tornado.web.Application(controllers, **settings)

        server = tornado.httpserver.HTTPServer(_app, xheaders=True)
        # server = tornado.httpserver.HTTPServer(_app, ssl_options={
        #     "certfile": os.path.join(cfg.data_path, 'cert', "server.pem"),
        #     "keyfile": os.path.join(cfg.data_path, 'cert', "server.key"),
        # })

        try:
            server.listen(cfg.common.port, address=cfg.common.ip)
            if cfg.common.ip == '0.0.0.0':
                log.i('works on [http://127.0.0.1:{}]\n'.format(cfg.common.port))
            else:
                log.i('works on [http://{}:{}]\n'.format(cfg.common.ip, cfg.common.port))
        except:
            log.e('can not listen on port {}:{}, make sure it not been used by another application.\n'.format(cfg.common.ip, cfg.common.port))
            return 0

        try:
            tornado.ioloop.IOLoop.instance().start()
        except:
            log.e('\n')

        return 0


def tp_web_app():
    """
    取得WebApp的唯一实例

    :rtype : WebApp
    """

    import builtins
    if '__web_app__' not in builtins.__dict__:
        builtins.__dict__['__web_app__'] = WebApp()
    return builtins.__dict__['__web_app__']
