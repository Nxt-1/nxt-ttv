import logging
import multiprocessing
import sys

from twitchio.ext import eventsub, pubsub

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
    database.create_raffle_table()
    bot = NxtBot(token=args.token, own_id=args.own_id, prefix=('?', '!'), client_secret=args.client_secret,
                 client_id=args.client_id)

    @bot.twitch_bot.event()
    async def event_pubsub_subscription(event: pubsub.PubSubChannelSubscribe):
        # Handle anon subs
        if event.context in ('anonsubgift', 'anonresubgift'):
            event.user.name = 'anonymous'

        if event.is_gift:
            module_logger.info('New gifted sub from ' + str(event.user.name) + ' to ' + str(event.recipient.name))

            channel_user = await event.channel.user()
            channel_id = channel_user.id
            database.increment_subs(int(event.user.id), event.user.name, channel_id)
            (subs, bits, redeems) = database.get_counts_from_name(event.user.name, channel_id)
            module_logger.info('Subs: ' + str(subs) + ' bits: ' + str(bits) + ' redeems: ' + str(redeems))
        else:
            module_logger.info('Sub from ' + str(event.user.name))
            channel_user = await event.channel.user()
            channel_id = channel_user.id
            database.increment_subs(int(event.user.id), event.user.name, channel_id)
            (subs, bits, redeems) = database.get_counts_from_name(event.user.name, channel_id)
            module_logger.info('Subs: ' + str(subs) + ' bits: ' + str(bits) + ' redeems: ' + str(redeems))

        sub_count = database.get_total_subs(channel_id)
        # TODO: Make this number dynamic in the config
        if (sub_count % 100) == 0:
            await channel_user.chat_announcement(bot.twitch_bot.own_token, bot.twitch_bot.own_id, 'We\'re up to ' +
                                                 str(sub_count) + ' subs now, time for a raffle! (use !raffle)', 'blue')

    @bot.twitch_bot.event()
    async def event_pubsub_bits(event: pubsub.PubSubBitsMessage):
        module_logger.info(str(event.user.name) + ' gave ' + str(event.bits_used))

        database.increment_bits(event.user.id, event.user.name, int(event.channel_id), event.bits_used)
        (subs, bits, redeems) = database.get_counts_from_name(event.user.name, int(event.channel_id))
        module_logger.info('Subs: ' + str(subs) + ' bits: ' + str(bits) + ' redeems: ' + str(redeems))

    @bot.twitch_bot.event()
    async def event_pubsub_channel_points(event: pubsub.PubSubChannelPointsMessage):
        module_logger.debug(str(event.user.name) + ' redeemed ' + str(event.reward.title))

        database.increment_redeems(event.user.id, event.user.name, int(event.channel_id))
        (subs, bits, redeems) = database.get_counts_from_name(event.user.name, int(event.channel_id))
        module_logger.debug('Subs: ' + str(subs) + ' bits: ' + str(bits) + ' redeems: ' + str(redeems))

    @bot.twitch_bot.esbot.event()
    async def event_eventsub_notification_ban(payload: eventsub.NotificationEvent) -> None:
        module_logger.critical('Received ban event for ' + str(payload.data.user.name) + ' in channel ' +
                               str(payload.data.broadcaster.name))
        # Update the database
        database.update_status(int(payload.data.user.id), database.FilterEventStatus.BANNED)

    @bot.twitch_bot.esbot.event()
    async def event_eventsub_notification_unban(payload: eventsub.NotificationEvent) -> None:
        module_logger.critical('Received unban event for ' + str(payload.data.user.name) + ' in channel ' +
                               str(payload.data.broadcaster.name))
        # Update the database
        database.update_status(int(payload.data.user.id), database.FilterEventStatus.UNBANNED)

    @bot.twitch_bot.esbot.event()
    async def event_eventsub_notification_channel_shield_mode_end(event: eventsub.NotificationEvent) -> None:
        module_logger.critical('Received unshield event')

    bot.run()

    module_logger.info('Bot exited')
    if not global_terminator.is_term.is_set():
        global_terminator.do_terminate(0)

    sys.exit(global_terminator.exit_code.value)


if __name__ == "__main__":
    main()
