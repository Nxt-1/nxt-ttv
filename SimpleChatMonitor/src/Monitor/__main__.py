import logging
import multiprocessing
import sys
import time

from Monitor.Utils import Logging, Utils, Constants

module_logger = logging.getLogger(__name__)


def main():
    # <editor-fold desc="Application init">
    # Check if essential folders exist or can be made
    # try:
    #     Utils.check_folder(Constants.LOGS_PATH, use_logging=False)
    # except (PermissionError, FileNotFoundError):
    #     # Logging folder may not be available
    #     sys.stderr.write('One or more output folder does not exist and could not be created, fatal error!\n')
    #     sys.exit(4)
    # else:
    #     sys.stdout.write('[Info] Essential output folders are available\n')

    from_process_pipe, process_pipe = multiprocessing.Pipe()
    global_terminator = Utils.GlobalTerminator(from_process_pipe, process_pipe)
    global_terminator.daemon = True
    global_terminator.start()
    # </editor-fold>

    # <editor-fold desc="Logging">
    # Setup multi-processing logging listener
    log_queue = multiprocessing.Queue(-1)
    log_listener = Logging.LogListener(log_queue, Constants.LOGGING_LEVEL, global_terminator.is_term)
    log_listener.start()

    # Configure logging for this module
    Logging.log_worker_configurer(log_queue, Constants.LOGGING_LEVEL)
    # module_logger.info('Logging into folder: ' + str(Constants.LOGS_PATH))

    # </editor-fold>

    module_logger.info('Nxt Twitch chat monitor is ready')
    time.sleep(3)
    module_logger.debug('Sleep done')
    module_logger.info('Sleep done')
    module_logger.warning('Sleep done')
    module_logger.error('Sleep done')
    module_logger.critical('Sleep done')
    time.sleep(0.1)

    global_terminator.is_term.set()

    sys.exit(global_terminator.exit_code.value)


if __name__ == "__main__":
    main()
