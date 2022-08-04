import logging.handlers
import multiprocessing
import sys
import time
from typing import Optional

from ..version import __version__

module_logger = logging.getLogger(__name__)


def add_logging_level(level_name, level_num, method_name=None):
    """
    Comprehensively adds a new logging level to the `logging` module and the
    currently configured logging class.

    `level_name` becomes an attribute of the `logging` module with the value
    `level_num`. `method_name` becomes a convenience method for both `logging`
    itself and the class returned by `logging.getLoggerClass()` (usually just
    `logging.Logger`). If `method_name` is not specified, `level_name.lower()` is
    used.

    To avoid accidental clobbering of existing attributes, this method will
    raise an `AttributeError` if the level name is already an attribute of the
    `logging` module or if the method name is already present

    Example
    -------
    # >>> add_logging_level('TRACE', logging.DEBUG - 5)
    # >>> logging.getLogger(__name__).setLevel("TRACE")
    # >>> logging.getLogger(__name__).trace('that worked')
    # >>> logging.trace('so did this')
    # >>> logging.TRACE
    5

    """
    if not method_name:
        method_name = level_name.lower()

    if hasattr(logging, level_name):
        raise AttributeError('{} already defined in logging module'.format(level_name))
    if hasattr(logging, method_name):
        raise AttributeError('{} already defined in logging module'.format(method_name))
    if hasattr(logging.getLoggerClass(), method_name):
        raise AttributeError('{} already defined in logger class'.format(method_name))

    # This method was inspired by the answers to Stack Overflow post
    # http://stackoverflow.com/q/2183233/2988730, especially
    # http://stackoverflow.com/a/13638084/2988730
    def log_for_level(self, message, *args, **kwargs):
        if self.isEnabledFor(level_num):
            self._log(level_num, message, args, **kwargs)

    def log_to_root(message, *args, **kwargs):
        logging.log(level_num, message, *args, **kwargs)

    logging.addLevelName(level_num, level_name)
    setattr(logging, level_name, level_num)
    setattr(logging.getLoggerClass(), method_name, log_for_level)
    setattr(logging, method_name, log_to_root)


# Add the extra level here already, so the CustomFormatter can use it
add_logging_level('CMD', logging.CRITICAL + 5)


class CustomFormatter(logging.Formatter):
    grey = "\x1b[37m"
    green = "\x1b[32m"
    yellow = "\x1b[33m"
    red = "\x1b[31m"
    bold_red = "\x1b[31;1m"
    purple = "\x1b[35m"
    okblue = '\033[94m'
    reset = "\x1b[0m"
    format = 'v' + str(__version__) + ' %(asctime)s [%(levelname)-8s] [%(name)s - %(funcName)s]  %(message)s'

    FORMATS = {
        logging.DEBUG   : grey + format + reset,
        logging.INFO    : green + format + reset,
        logging.WARNING : yellow + format + reset,
        logging.ERROR   : bold_red + format + reset,
        logging.CRITICAL: purple + format + reset,
        logging.CMD   : okblue + format + reset,
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


class LogListener(multiprocessing.Process):
    """
    The process that reads all logging messages from the queue and processes them properly.

    :param log_queue: Queue for all logging messages
    :param log_lvl: The level of logging
    """

    def __init__(self, log_queue: multiprocessing.Queue, log_lvl: str, global_is_term: multiprocessing.Event()) -> None:
        multiprocessing.Process.__init__(self)
        self.global_is_term = global_is_term
        self.log_queue = log_queue  # Actual queue object where logs will be placed on
        self.log_lvl = log_lvl

    def run(self) -> None:
        logging.getLogger(__name__).setLevel(str_to_log_lvl(self.log_lvl))
        # Setup handlers and formatters #
        root_logger = logging.getLogger()
        # Logging - setup console handler
        log_console_h = logging.StreamHandler()
        # Logging - setup file handler
        # log_file_h = logging.handlers.RotatingFileHandler(Constants.LOGS_PATH + '/Monitor.log', maxBytes=0,
        #                                                        backupCount=10)
        # Logging - apply the formatter and handlers
        log_console_h.setFormatter(CustomFormatter())
        # log_file_h.setFormatter(CustomFormatter())
        # Logging - adding handlers to the root logger
        root_logger.addHandler(log_console_h)
        # root_logger.addHandler(log_file_h)

        error_msg: Optional[str] = None  # Placeholder for the eventual exit reason
        while not self.global_is_term.is_set():
            # Normal log processing
            try:
                record = self.log_queue.get()
                if record is None:
                    break
                logger = logging.getLogger(record.name)
                logger.handle(record)
            except KeyboardInterrupt:
                error_msg = 'KeyboardInterrupt'
                break
            except (IOError, EOFError, BrokenPipeError, ConnectionResetError) as e:
                error_msg = 'pipe broke: ' + str(e)
                break
            except Exception as e:
                error_msg = 'unexpected exit: ' + str(e)
                break

            time.sleep(0)

        sys.stdout.write('\nLogger exited - further logging will not be processed: ' + error_msg + '\n')


def log_worker_configurer(log_queue, log_lvl: str) -> None:
    """
    Configures everything logging related for workers

    :param log_queue: Queue for all logging messages
    :param log_lvl: The level of logging
    """

    h = logging.handlers.QueueHandler(log_queue)
    logger = logging.getLogger()
    # Prevent handler duplicates
    if logger.hasHandlers():
        logger.handlers.clear()
    logger.addHandler(h)

    # Logging - set level
    logger.setLevel(str_to_log_lvl(log_lvl))


def str_to_log_lvl(log_str: str) -> int:
    """
    Helper function to convert string names of log levels to values that the logging modules can use.

    :param log_str: The string name of the log level
    :return: The logging style value
    """

    if log_str == 'critical':
        log_lvl = logging.CRITICAL
    elif log_str == 'error':
        log_lvl = logging.ERROR
    elif log_str == 'warning':
        log_lvl = logging.WARNING
    elif log_str == 'info':
        log_lvl = logging.INFO
    elif log_str == 'debug':
        log_lvl = logging.DEBUG
    else:
        raise ValueError('Log level string could not be matched')

    return log_lvl
