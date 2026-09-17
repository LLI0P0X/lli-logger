import asyncio
import datetime
import logging
import logging.handlers
import os
import zipfile
import atexit as _atexit
import sys as _sys

__all__ = ['logger']


def _to_level(level):
    """Accepts either an int level or a level name ('INFO', 'DEBUG', ...) and
    returns the numeric logging level."""
    if isinstance(level, int):
        return level
    return logging.getLevelName(str(level).upper())


class Logger(logging.Logger):
    """A logging.Logger subclass with an optional Telegram notification
    channel (notify / notify_sync / notify_async)."""

    def __init__(self,
                 name='app',
                 level=logging.DEBUG,
                 tg_notify=False,
                 tg_token=None,
                 tg_ids=None,
                 time_func=datetime.datetime.now):
        super().__init__(name, level)
        self.tg_notify = tg_notify
        self.time_func = time_func
        self.tg_token = tg_token
        self.tg_ids = tg_ids or []

        if tg_notify:
            try:
                import aiohttp  # noqa: F401
                import requests  # noqa: F401
                if not (tg_token or self.tg_ids):
                    import config
                if not tg_token:
                    self.tg_token = config.BOT_TOKEN
                if not self.tg_ids:
                    self.tg_ids = config.TOP_ADMINS
            except (ImportError, ModuleNotFoundError, AttributeError):
                self.warning(
                    'TG error, tg_notify is set to False || '
                    'You need to install the aiohttp and requests libraries for tg_notify to work || '
                    'You need to set BOT_TOKEN and TOP_ADMINS in config.py or pass tg_token and tg_ids to Logger'
                )
                self.tg_notify = False

    async def notify_async(self, level, message):
        import aiohttp
        msg = f"lvl: {level}\nserver time: {self.time_func().strftime('%Y-%m-%d %H:%M:%S')}\n\n{message}"
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

        self.log(_to_level(level), message, stacklevel=3)

    def notify_sync(self, level, message):
        import requests
        msg = f"lvl: {level}\nserver time: {self.time_func().strftime('%Y-%m-%d %H:%M:%S')}\n\n{message}"
        url = f"https://api.telegram.org/bot{self.tg_token}/sendMessage"

        for _id in self.tg_ids:
            try:
                resp = requests.post(url, json={"chat_id": _id, "text": msg}, timeout=10)
                if resp.status_code != 200:
                    self.error(f"TG notify failed for {_id}: {resp.status_code}, {resp.text}")
            except Exception as e:
                self.error(f"TG notify exception for {_id}: {e}")

        self.log(_to_level(level), message, stacklevel=3)

    def notify(self, level, message, force_sync=False):
        if not self.tg_notify:
            self.warning("tg_notify is False")
            self.log(_to_level(level), message, stacklevel=2)
            return None
        try:
            if force_sync:
                raise RuntimeError
            loop = asyncio.get_running_loop()
            # Активный event loop -> отправляем асинхронно
            return loop.create_task(self.notify_async(level, message))
        except RuntimeError:
            # Loop не запущен -> отправляем синхронно
            self.notify_sync(level, message)
            return None


class ZipRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """RotatingFileHandler that zips the rolled-over log file instead of
    keeping it as plain text (mirrors loguru's rotation + compression)."""

    def doRollover(self):
        super().doRollover()
        rotated = f"{self.baseFilename}.1"
        if os.path.exists(rotated):
            zip_path = rotated + '.zip'
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                zf.write(rotated, os.path.basename(rotated))
            os.remove(rotated)


def setup_root_logging(level='INFO', ignored=None, handlers=None):
    """Route the standard `logging` module (third-party libraries, etc.)
    through the same handlers/format as our custom logger."""
    logging.basicConfig(
        level=_to_level(level),
        handlers=handlers or [],
        force=True,
    )
    for name in (ignored or []):
        logging.getLogger(name).disabled = True


# ---------------------------------------------------------------------------
# Module-level singleton logger setup
# ---------------------------------------------------------------------------

logging.setLoggerClass(Logger)

logger = Logger('app', level=logging.DEBUG, tg_notify=True)
logger.propagate = False

_formatter = logging.Formatter(
    fmt='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)

console_handler = logging.StreamHandler(_sys.stderr)
console_handler.setFormatter(_formatter)
logger.addHandler(console_handler)

logDir = os.path.join(os.getcwd(), 'logs')
os.makedirs(logDir, exist_ok=True)
logPath = os.path.join(
    logDir,
    f"log_{logger.time_func().strftime('d%Y-%m-%dt%H-%M-%S')}.log",
)

file_handler = ZipRotatingFileHandler(
    logPath,
    mode='w',
    maxBytes=1_000_000,  # 1 MB
    backupCount=1,
    encoding='utf-8',
)
file_handler.setFormatter(_formatter)
logger.addHandler(file_handler)

_atexit.register(logging.shutdown)

# Route stdlib `logging` calls (from third-party libs) through the same
# handlers/format as our logger.
setup_root_logging('INFO', handlers=[console_handler, file_handler])

if __name__ == '__main__':
    logger.info('hello logs')
