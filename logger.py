import asyncio
import logging
import os
import datetime
import inspect

from loguru import _logger
from loguru import _defaults

import atexit as _atexit
import sys as _sys

__all__ = ['logger']

def get_depth(frame):
    depth = 0
    while frame.f_code.co_filename in [logging.__file__, __file__]:
        frame = frame.f_back
        depth += 1
    return depth


class Logger(_logger.Logger):
    def __init__(self,
                 tg_notify=False,
                 tg_token=None,
                 tg_ids=[],
                 time_func=datetime.datetime.now,
                 core=_logger.Core(),
                 exception=None,
                 depth=0,
                 record=False,
                 lazy=False,
                 colors=False,
                 raw=False,
                 capture=True,
                 patchers=[],
                 extra={},
                 ):
        super(Logger, self).__init__(core, exception, depth, record, lazy, colors, raw, capture, patchers, extra)
        self.tg_notify = tg_notify
        self.time_func = time_func
        if tg_notify:
            try:
                import asyncio
                import requests
                import aiohttp
                if not (tg_token or tg_ids):
                    import config
                if tg_token:
                    self.tg_token = tg_token
                else:
                    self.tg_token = config.BOT_TOKEN

                if tg_ids:
                    self.tg_ids = tg_ids
                else:
                    self.tg_ids = config.TOP_ADMINS
            except (ImportError, ModuleNotFoundError, AttributeError):
                self.warning('TG error, tg_notify is set to False || '
                             'You need to install the aiohttp and requests libraries for tg_notify to work ||'
                             'You need to set BOT_TOKEN and TOP_ADMINS in config.py or pass tg_token and tg_ids to Logger')
                self.tg_notify = False

    def opt_log(self, level, message, *args, **kwargs):
        depth = get_depth(inspect.currentframe())
        super().opt(depth=depth).log(level, message, *args, **kwargs)

    async def notify_async(self, level, message):
        import aiohttp
        msg = f"lvl: {level}\nserver time:{self.time_func().strftime('%Y-%m-%d %H:%M:%S')}\n\n{message}"
        url = f"https://api.telegram.org/bot{self.tg_token}/sendMessage"

        async with aiohttp.ClientSession() as session:
            for _id in self.tg_ids:
                try:
                    async with session.post(url, json={"chat_id": _id, "text": msg}) as resp:
                        if resp.status != 200:
                            body = await resp.text()
                            self.error(f"TG notify failed for {_id}: {resp.status}, {body}")
                except Exception as e:
                    self.error(f"TG notify exception for {_id}: {e}")

        self.opt_log(level, message)

    def notify_sync(self, level, message):
        import requests
        msg = f"lvl: {level}\nserver time:{self.time_func().strftime('%Y-%m-%d %H:%M:%S')}\n\n{message}"
        url = f"https://api.telegram.org/bot{self.tg_token}/sendMessage"

        for _id in self.tg_ids:
            try:
                resp = requests.post(url, json={"chat_id": _id, "text": msg}, timeout=10)
                if resp.status_code != 200:
                    self.error(f"TG notify failed for {_id}: {resp.status_code}, {resp.text}")
            except Exception as e:
                self.error(f"TG notify exception for {_id}: {e}")

        self.opt_log(level, message)

    def notify(self, level, message, force_sync=False):
        if not self.tg_notify:
            self.warning("tg_notify is False")
            self.opt_log(level, message)
            return None
        try:
            if force_sync:
                raise RuntimeError
            loop = asyncio.get_running_loop()
            # Если есть активный loop → запускаем асинхронно
            return loop.create_task(self.notify_async(level, message))
        except RuntimeError:
            # Если loop закрыт → используем sync
            self.notify_sync(level, message)
            return None


class InterceptHandler(logging.Handler):
    def setup_logger(
            level: str | int = 'DEBUG',
            ignored: list[str] = ''
    ):
        logging.basicConfig(
            handlers=[InterceptHandler()],
            level=logging.getLevelName(level)
        )
        for ignore in ignored:
            logger.disable(ignore)

    def emit(self, record):
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame = logging.currentframe()
        depth = get_depth(frame)
        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


logger = Logger(tg_notify=True)

if _defaults.LOGURU_AUTOINIT and _sys.stderr:
    logger.add(_sys.stderr)
_atexit.register(logger.remove)

logDir = os.path.join(os.getcwd(), 'logs')
logPath = os.path.join(logDir, f'log_{logger.time_func().strftime('d%Y-%m-%dt%H-%M-%S')}.log')

logger.add(logPath, mode='w', format='{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}', encoding='utf-8',
           rotation='1 MB', compression='zip')

InterceptHandler.setup_logger('INFO')

if __name__ == '__main__':
    logger.info('hello logs')
