# -*- coding: utf-8 -*-
import logging
import re
import sys
import traceback
from contextlib import suppress
from types import TracebackType
from typing import Type


class SensitiveFormatter(logging.Formatter):
    """Formatter that removes sensitive info."""

    @staticmethod
    def _filter(s):
        # Dict filter
        s = re.sub(r"('_pull_secret':\s+)'(.*?)'", r"\g<1>'*** PULL_SECRET ***'", s)
        s = re.sub(r"('_ssh_public_key':\s+)'(.*?)'", r"\g<1>'*** SSH_KEY ***'", s)
        s = re.sub(r"('_vsphere_username':\s+)'(.*?)'", r"\g<1>'*** VSPHERE_USER ***'", s)
        s = re.sub(r"('_vsphere_password':\s+)'(.*?)'", r"\g<1>'*** VSPHERE_PASSWORD ***'", s)

        # Object filter
        s = re.sub(r"(pull_secret='[^']*(?=')')", "pull_secret = *** PULL_SECRET ***", s)
        s = re.sub(r"(ssh_public_key='[^']*(?=')')", "ssh_public_key = *** SSH_KEY ***", s)
        s = re.sub(r"(vsphere_username='[^']*(?=')')", "vsphere_username = *** VSPHERE_USER ***", s)
        s = re.sub(r"(vsphere_password='[^']*(?=')')", "vsphere_password = *** VSPHERE_PASSWORD ***", s)

        return s

    def format(self, record):
        original = logging.Formatter.format(self, record)
        return self._filter(original)


class ColorizingStreamHandler(logging.StreamHandler):
    BLUE = "\033[0;34m"
    LIGHT_RED = "\033[1;31m"
    LIGHT_YELLOW = "\033[1;33m"
    LIGHT_BLUE = "\033[1;34m"
    LIGHT_PURPLE = "\033[1;35m"
    LIGHT_CYAN = "\033[1;36m"
    WHITE = "\033[1;37m"
    RESET = "\033[0m"

    def __init__(self, *args, **kwargs):
        self._colors = {
            logging.DEBUG: self.BLUE,
            logging.INFO: self.RESET,
            logging.WARNING: self.LIGHT_YELLOW,
            logging.ERROR: self.LIGHT_RED,
            logging.CRITICAL: self.LIGHT_PURPLE,
        }
        super().__init__(*args, **kwargs)

    @property
    def is_tty(self):
        isatty = getattr(self.stream, "isatty", None)
        return isatty and isatty()

    def emit(self, record):
        try:
            message = self.format(record)
            stream = self.stream
            if not self.is_tty:
                stream.write(message)
            else:
                message = self._colors[record.levelno] + message + self.RESET
                stream.write(message)
            stream.write(getattr(self, "terminator", "\n"))
            self.flush()
        except Exception:
            self.handleError(record)


logging.getLogger("requests").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)

log = logging.getLogger("")
log.setLevel(logging.DEBUG)


def add_log_file_handler(filename: str) -> logging.FileHandler:
    fmt = SensitiveFormatter("%(asctime)s - %(name)s - %(levelname)s - %(thread)d - %(message)s")
    fh = logging.FileHandler(filename)
    fh.setFormatter(fmt)
    log.addHandler(fh)
    return fh


def add_stream_handler():
    fmt = SensitiveFormatter("%(asctime)s %(levelname)-10s - %(thread)d - %(message)s \t" "(%(pathname)s:%(lineno)d)")
    ch = ColorizingStreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    log.addHandler(ch)


add_log_file_handler("test_infra.log")
add_stream_handler()


class SuppressAndLog(suppress):
    def __exit__(self, exctype: Type[Exception], excinst: Exception, exctb: TracebackType):
        res = super().__exit__(exctype, excinst, exctb)

        if res:
            with suppress(BaseException):
                tb_data = traceback.extract_tb(exctb, 1)[0]
                log.warning(f"Suppressed {exctype.__name__} from {tb_data.name}:{tb_data.lineno} : {excinst}")

        return res
