import logging
import multiprocessing
import sys

from twitchio.ext import eventsub

from Monitor import database
from Monitor.Utils import monitor_logging, utils, constants
from Monitor.bot import NxtBot

module_logger = logging.getLogger(__name__)


def main():
    # <editor-fold desc="Application init">
    # Parse arguments
    parser = utils.setup_arg_parser()
    args = parser.parse_args()

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
    global_terminator = utils.GlobalTerminator(from_process_pipe, process_pipe)
    global_terminator.daemon = True
    global_terminator.start()
    # </editor-fold>

    # <editor-fold desc="Logging">
    # Setup multi-processing logging listener
    log_queue = multiprocessing.Queue(-1)
    log_listener = monitor_logging.LogListener(log_queue, constants.LOGGING_LEVEL, global_terminator.is_term)
    log_listener.start()

    # Configure logging for this module
    monitor_logging.log_worker_configurer(log_queue, constants.LOGGING_LEVEL)

    logging.getLogger('twitchio').setLevel(logging.INFO)

    # </editor-fold>

    module_logger.info('Nxt Twitch chat monitor is ready')
    db_connection = database.get_connection()
    database.create_filter_table()
    bot = NxtBot(token=args.token, own_id=args.own_id, prefix='?')

    @bot.twitch_bot.esbot.event()
    async def event_eventsub_notification_ban(payload: eventsub.ChannelBanData) -> None:
        module_logger.critical('Received ban event')

    @bot.twitch_bot.esbot.event()
    async def event_eventsub_notification_unban(payload: eventsub.ChannelUnbanData) -> None:
        module_logger.critical('Received unban event HYPE')

    @bot.twitch_bot.esbot.event()
    async def event_eventsub_notification_channel_shield_mode_end(event: eventsub.ChannelShieldModeEndData) -> None:
        module_logger.critical('Received unshield event')

    bot.run()

    module_logger.info('Bot exited')
    if not global_terminator.is_term.is_set():
        global_terminator.do_terminate(0)

    sys.exit(global_terminator.exit_code.value)


if __name__ == "__main__":
    main()
