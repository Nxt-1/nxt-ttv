import asyncio
import json
import logging
import multiprocessing
import os
from typing import Union, Callable, Coroutine, Optional, Dict, List

import twitchio
from twitchio.ext import commands, eventsub, pubsub

from Monitor import database
from Monitor.Utils import constants
from Monitor.Utils.custom_errors import CancelError
from Monitor.Utils.utils import JoinChannels, JoinChannel
from Monitor.twitchbot_functions.gambling import GambleParser
from Monitor.twitchbot_functions.message_filter import MessageChecker, BanEvent, CheckResult, CheckResultType, \
    IgnoreReason
from Monitor.twitchbot_functions.notifications import Notifier
from Monitor.twitchbot_functions.voting import Voter

module_logger = logging.getLogger(__name__)


class TwitchBot(commands.Bot):
    def __init__(self, own_token: str, own_id: int, prefix: Union[str, list, tuple, set, Callable, Coroutine],
                 client_secret: str = None, client_id: str = None, heartbeat: Optional[float] = 30.0, **kwargs):
        self.join_channels = JoinChannels()  # List of channels and their details that the bot is joined to
        self.read_auth_file(constants.AUTH_PATH)
        super().__init__(token=own_token, prefix=prefix, client_secret=client_secret, client_id=client_id,
                         initial_channels=self.join_channels.get_channel_name_list(), heartbeat=heartbeat,
                         kwargs=kwargs)
        self.pubsub = pubsub.PubSubPool(self)
        self.esbot = commands.Bot.from_client_credentials(client_secret=client_secret, client_id=client_id)
        self.esclient = eventsub.EventSubClient(self.esbot, webhook_secret='veryverysecretstring',
                                                callback_route='https://nxt-3d.be/twitchhook')
        self.own_id = own_id  # We need this before we're logged into the API for the pubsub
        self.own_token = own_token
        self.mp_manager = multiprocessing.Manager()
        self.spam_bot_filter = MessageChecker(joined_channels=self.join_channels, cyrillics_score=10)
        self.ban_events: Dict[
            str, BanEvent] = {}  # Dict containing all the currently active BanEvents (the author's name is used as key)
        self.gamble_bot = GambleParser('nxthammerboi', self.loop)
        self.break_voter = Voter(self.mp_manager, votes_required=3, vote_period=60, fail_timeout_s=10 * 60,
                                 pass_timeout_s=3 * 60 * 60, double_names={'ninariiofcannith', 'MistressViolet68'},
                                 announce_message='We are voting to make Deathy take 3 minute break. '
                                                  'Vote by typing ?votebreak')
        self.notifier = Notifier()

    async def __ainit__(self):
        for channel in self.join_channels.channels.values():
            if channel.enable_raffle_module:
                # Pubsub stuff
                topics = [
                    pubsub.channel_points(channel.token)[int(channel.twitch_id)],
                    pubsub.bits(channel.token)[int(channel.twitch_id)],
                    pubsub.channel_subscriptions(channel.token)[int(channel.twitch_id)]
                ]
                await self.pubsub.subscribe_topics(topics)

        # Eventsub stuff
        self.loop.create_task(self.esclient.listen(port=4000))
        # self.loop.create_task(self.eventsub_client.listen(port=4000))

        # TODO: Subscribe to all joined channels
        try:
            await self.esclient.subscribe_channel_unbans(broadcaster=38884531)
        except twitchio.HTTPException as e:
            module_logger.error('HTTP exception for webhook1: ' + str(e))

        try:
            await self.esclient.subscribe_channel_bans(broadcaster=38884531)
        except twitchio.HTTPException as e:
            module_logger.error('HTTP exception for webhook2: ' + str(e))

        try:
            # await esclient.subscribe_channel_bans(broadcaster=38884531)
            await self.esclient.subscribe_channel_shield_mode_end(broadcaster=38884531, moderator=38884531)
        except twitchio.HTTPException as e:
            module_logger.error('HTTP exception for webhook3: ' + str(e))

        await self.start()

    def read_auth_file(self, file_path: str) -> None:
        # TODO: Refactor to read config
        """
        Parses the config file containing the auth configuration.

        :param file_path: Path to the auth file
        """

        try:
            with open(os.path.abspath(file_path)) as auth_file:
                auth_json = json.load(auth_file)
        except FileNotFoundError as e:
            module_logger.error('Could not find auth file at ' + str(os.path.abspath(file_path)) + ': ' + str(e))
            return
        else:
            # Read the channels to join
            for channel in auth_json['channels']:
                debug_msg = 'Joining channel ' + str(channel)
                twitch_id = None
                enable_raffle_module = False
                if auth_json['channels'][channel]['id']:
                    debug_msg += ' with ID'
                    twitch_id = auth_json['channels'][channel]['id']
                token = None
                if auth_json['channels'][channel]['token']:
                    debug_msg += ' and token'
                    token = auth_json['channels'][channel]['token']
                if auth_json['channels'][channel]['raffle-module']:
                    debug_msg += ' | raffle module'
                    enable_raffle_module = auth_json['channels'][channel]['raffle-module']
                join_channel = JoinChannel(channel, twitch_id, token, enable_raffle_module)

                module_logger.info(debug_msg)
                self.join_channels.append_channel(join_channel)

    async def event_ready(self):
        module_logger.info('Bot is live, logged in as ' + str(self.nick))

    @commands.command()
    async def hello(self, ctx: commands.Context):
        await ctx.send('Hello ' + str(ctx.author.name) + ', I am an automated bot made by nxt__1')

    @commands.command(aliases=('quit', 'q', 'stop'))
    async def leave(self, ctx: commands.Context):
        module_logger.warning('Leave command received, closing')
        if ctx.author.is_broadcaster or ctx.author.is_mod:
            await ctx.send('Hello ' + str(ctx.author.name) + ', I will be leaving your channel now')
            await self.close()
        else:
            await ctx.send('Hello ' + str(ctx.author.name) +
                           ', only channel staff are allowed to use this command')

    @commands.command()
    async def goal(self, ctx: commands.Context):
        await ctx.send('Hi, I am a bot and for now my only goal is boot pesky spam/phishing bots out of here. Oh, and '
                       'world dominion of course.')

    @commands.command()
    async def fp(self, ctx: commands.Context):
        # TODO: Check user roles
        # TODO: Delete this once the untimeout system is in place

        # Check that a name was passed
        if ctx.prefix + ctx.command.name == ctx.message.content:
            module_logger.info('No name specified in fp command (' + ctx.message.content + '), ignoring')
            await ctx.send('No name specified, try ' + ctx.prefix + ctx.command.name + ' name')
            return

        # Extract the name
        name = ctx.message.content.replace(ctx.prefix + ctx.command.name + ' ', '')
        # Remove an @ if it was passed
        name = name.replace('@', '')

        try:
            await self.ban_events[name].cancel()
            self.remove_ban_event(name)
            await self.unban_chatter(channel=ctx.channel, chatter_name=name)
        except KeyError:
            module_logger.warning('No open ban event for user ' + str(name) + ' found')
            await ctx.send('No open ban event for user ' + str(name) + ' found')
        except CancelError as e:
            module_logger.error('Cancel error: ' + str(e))
            await ctx.send(str(e))
        else:
            module_logger.info('Open ban event for user ' + str(name) + ' is removed')
            await ctx.send('Ban event for ' + str(name) + ' successfully canceled')

    @commands.command()
    async def reload(self, ctx: commands.Context):
        """
        Triggers a reload for the filter
        """

        module_logger.warning('Reloading filter config file')
        if ctx.author.is_broadcaster or ctx.author.is_mod:
            self.spam_bot_filter.read_config_file(constants.FILTER_CONFIG_PATH)
            await ctx.send('Reloaded complete, I feel even more powerful now')

    @commands.command()
    async def votebreak(self, ctx: commands.Context):
        """"
        Handles a user requesting a break vote
        """

        if ctx.channel.name == 'deathy_tv':
            await self.break_voter.add_vote(ctx.message)

    @commands.command(aliases=('subs', 'bits', 'redeems', 'check'))
    async def count(self, ctx: commands.Context):
        # Check that a name was passed
        if ctx.prefix + ctx.command.name == ctx.message.content:
            module_logger.info('No name specified in command (' + ctx.message.content + '), ignoring')
            await ctx.send('No name specified, try ' + ctx.prefix + ctx.command.name + ' <name>')
            return

        # Extract the name
        name = ctx.message.content.replace(ctx.prefix + ctx.command.name + ' ', '')
        # Remove an @ if it was passed
        name = name.replace('@', '')

        try:
            channel_user = await ctx.channel.user()
            channel_id = channel_user.id
            (subs, bits, redeems) = database.get_counts_from_name(name, channel_id)
        except IndexError:
            await ctx.send("I've looked everywhere, but couldn't find " + name)
        else:
            await ctx.send(name + ' currently has ' + str(subs) + ' gifted subs, ' + str(bits) +
                           ' bits redeemed and ' + str(redeems) + ' channel point redeems')

    @commands.command()
    async def tickets(self, ctx: commands.Context):
        # Check that a name was passed
        if ctx.prefix + ctx.command.name == ctx.message.content:
            module_logger.info('No name specified in command (' + ctx.message.content + '), ignoring')
            await ctx.send('No name specified, try ' + ctx.prefix + ctx.command.name + ' <name>')
            return

        # Extract the name
        name = ctx.message.content.replace(ctx.prefix + ctx.command.name + ' ', '')
        # Remove an @ if it was passed
        name = name.replace('@', '')

        try:
            channel_user = await ctx.channel.user()
            channel_id = channel_user.id
            tickets = database.calculate_raffle_tickets_from_name(name, channel_id)
        except IndexError:
            await ctx.send("I've looked everywhere, but couldn't find " + name)
        else:
            await ctx.send(name + ' currently has ' + str(tickets) + ' tickets in the raffle.')

    @commands.command()
    async def all_tickets(self, ctx: commands.Context):
        channel_user = await ctx.channel.user()
        channel_id = channel_user.id
        (total_users, total_tickets) = database.calculate_all_tickets(channel_id)
        await ctx.send('There are currently ' + str(total_tickets) + ' tickets in the raffle, spread over ' +
                       str(total_users) + ' generous gifters')

    @commands.command()
    async def raffle(self, ctx: commands.Context):
        if ctx.author.is_broadcaster or ctx.author.is_mod:
            channel_user = await ctx.channel.user()
            channel_id = channel_user.id
            (total_users, total_tickets) = database.calculate_all_tickets(channel_id)
            await ctx.send('Pulling one lucky winner out of ' + str(total_tickets) + ' tickets, spread over ' +
                           str(total_users) + ' generous gifters')
            await asyncio.sleep(3)
            winner = database.do_raffle(channel_id)
            await ctx.send(str(winner) + ' is the lucky one! They had ' +
                           str(database.calculate_raffle_tickets_from_name(winner, channel_id)) +
                           ' tickets in the raffle')

        else:
            await ctx.send('Hello ' + str(ctx.author.name) + ', only channel staff are allowed to use this command')

    @commands.command()
    async def manual_add(self, ctx: commands.Context):
        """
        Manually adds either subs/bits/redeems to a specific user.
        Syntax: ?manual_add <count> <type> <user>
        <count>: a number specifying how much of the type to add
        <type>: what category to add, can be either 'subs', 'bits' or 'redeems'
        <name>: the name of the chatter to update
        """

        module_logger.warning('Manually adding: ' + str(ctx.message.content))
        # Parse the message
        message = str(ctx.message.content)
        message = message.removeprefix(ctx.prefix + ctx.command.name + ' ')

        # Check that all the parts are there
        try:
            (count, add_type, name) = message.split(' ', 3)
        except ValueError:
            await ctx.send('Missing syntax, try ' + ctx.prefix + ctx.command.name + ' <count> <type> <user>')
            return
        # Check that the count is a number
        try:
            count = int(count)
        except (NameError, ValueError):
            await ctx.send('Invalid number entered: ' + str(count))
            return
        # Check that the add_type is one of the valid types
        if add_type not in ('subs', 'bits', 'redeems'):
            await ctx.send("Invalid type, try 'subs', 'bits' or 'redeems'")
            return

        # Remove an @ if it was passed
        name = name.replace('@', '')
        # Check that the chatter exists
        chatter: List[twitchio.User] = await self.fetch_users([name])
        if not chatter:
            await ctx.send("I've looked everywhere, but couldn't find " + name)
            return
        chatter: twitchio.User = chatter[0]

        # Check that the user is staff
        if ctx.author.is_broadcaster or ctx.author.is_mod:
            channel_user = await ctx.channel.user()
            channel_id = channel_user.id
            if add_type == 'subs':
                module_logger.warning('Manually adding ' + str(count) + ' subs to ' + str(chatter.name) + ' (' +
                                      str(chatter.id) + ')')
                database.increment_subs(chatter.id, chatter.name, channel_id, count)
            elif add_type == 'bits':
                module_logger.warning('Manually adding ' + str(count) + ' bits to ' + str(chatter.name) + ' (' +
                                      str(chatter.id) + ')')
                database.increment_bits(chatter.id, chatter.name, channel_id, count)
            else:
                module_logger.warning('Manually adding ' + str(count) + ' redeems to ' + str(chatter.name) + ' (' +
                                      str(chatter.id) + ')')
                database.increment_redeems(chatter.id, chatter.name, channel_id, count)
            await ctx.send('Manual add done')
        else:
            await ctx.send('Hello ' + str(ctx.author.name) + ', only channel staff are allowed to use this command')

    def add_ban_event(self, ban_event: BanEvent) -> None:
        """
        Stores a new BanEvent in the system.

        :param ban_event: The ban event to add
        """

        if ban_event.check_result.message.author.display_name in self.ban_events:
            module_logger.warning('User ' + str(ban_event.check_result.message.author.display_name) +
                                  ' is already in the ban events')
        else:
            module_logger.debug('Adding new ban event for user ' +
                                str(ban_event.check_result.message.author.display_name))
            self.ban_events[ban_event.check_result.message.author.display_name] = ban_event

    def remove_ban_event(self, name: str) -> None:
        """
        Remove a ban event for a user specified (display name). Note this does not untimeout/ban.

        :param name: The display name of the user to remove the ban event for
        """

        try:
            self.ban_events.pop(name)
        except KeyError as e:
            module_logger.warning('Failed to remove ban event for user ' + str(name) + ': ' + str(e))
        else:
            module_logger.info('Removed ban event for user ' + str(name))

    async def ban_chatter(self, message: twitchio.Message) -> None:
        """
        Executes the user ban and clear the ban event from the system
        """

        module_logger.info('Executing ban on ' + message.author.display_name)
        author_partial_chatter = await message.author.user()
        # Get the user object of the channel the message was sent in
        message_channel = await message.channel.user()
        try:
            await message_channel.ban_user(self.own_token, self.user_id, author_partial_chatter.id,
                                           "Spam bot filtered, contact a mod if this was a mistake")
            self.ban_events.pop(message.author.display_name)
        except twitchio.errors.HTTPException as e:
            if e.reason == 'The user specified in the user_id field is already banned.':
                module_logger.debug('User already banned')
            else:
                module_logger.error('Unexpected error: '+str(e))
        except KeyError:
            module_logger.debug('Ignoring duplicate delete for user ' + str(message.author.display_name))

    async def unban_chatter(self, message: twitchio.Message = None, channel: twitchio.channel = None,
                            chatter_name: str = None) -> None:
        """
        Removes a ban or timeout on a chatter based on a message object or a channel/chatter_name combo.
        """

        if message:
            chatter = await message.author.user()
            channel_user = await message.channel.user()
        elif channel and chatter_name:
            channel_user = await channel.user()
            chatter = channel.get_chatter(chatter_name)
            if not chatter:
                module_logger.error('Failed to fetch chatter \'' + str(chatter_name) + '\' to unban')
                return
        else:
            raise ValueError('Invalid set of arguments passed. Use either the message or channel+chatter_name')

        module_logger.warning('Unbanning ' + chatter.display_name)
        # Get the user object of the channel the message was sent in
        await channel_user.unban_user(self.own_token, self.user_id, chatter.id)

    async def timeout_chatter(self, message: twitchio.Message) -> None:
        """
        Time's the user out.
        :param message: the message that will be used to extract the offending chatter from
        """

        author_partial_chatter = await message.author.user()
        # Get the user object of the channel the message was sent in
        message_channel = await message.channel.user()
        await message_channel.timeout_user(self.own_token, self.user_id, author_partial_chatter.id,
                                           constants.MINUTES_BEFORE_BAN * 60,
                                           "Spam bot filtered, contact a mod if this was a mistake")

        # TODO: Implement this properly
        if message.channel.name == 'belishhhh':
            await asyncio.sleep(0.5)
            await message.channel.send("!tts stop")

    async def handle_check_result(self, check_result: CheckResult):
        # Handle matches
        if check_result.result_type == CheckResultType.MATCH:
            module_logger.info('Flagged message from ' + check_result.message.author.display_name + ' in ' +
                               str(check_result.message.channel.name) + ' with:\n' +
                               '    Score: ' + str(check_result.message_score) + '\n' +
                               '    Message: ' + str(check_result.message.content) + '\n' +
                               '    Follow time mult.: ' + str(check_result.multipliers.follow_time) + '\n' +
                               '    First time chatter mult.: ' + str(check_result.multipliers.first_time_chatter))
            # Create a new ban event and start the timer
            ban_event = BanEvent(check_result, self.ban_chatter(check_result.message))
            self.add_ban_event(ban_event)
            await self.timeout_chatter(check_result.message)
            await ban_event.start()

        elif check_result.result_type == CheckResultType.IGNORED:
            # Don't log friendly bot results
            if check_result.ignore_reason == IgnoreReason.FRIENDLY_BOT:
                pass
            else:
                module_logger.info('Passing message from ' + check_result.message.author.display_name + ' in ' +
                                   str(check_result.message.channel.name) + ' with:\n' +
                                   '    Pass reason: ' + str(check_result.ignore_reason.name) + '\n' +
                                   '    Score: ' + str(check_result.message_score) + '\n' +
                                   '    Message: ' + str(check_result.message.content) + '\n' +
                                   '    Follow time mult.: ' + str(check_result.multipliers.follow_time) + '\n' +
                                   '    First time chatter mult.: ' + str(check_result.multipliers.first_time_chatter))
                await check_result.message.channel.send('@' + check_result.message.author.display_name +
                                                        ' You get a pass because: ' +
                                                        str(check_result.ignore_reason.name))

        # Log near misses
        elif check_result.result_type == CheckResultType.NO_MATCH and check_result.message_score >= 2:
            module_logger.debug('Near miss from ' + check_result.message.author.display_name + ' in ' +
                                str(check_result.message.channel.name) + ' with:\n' +
                                '    Score: ' + str(check_result.message_score) + '\n' +
                                '    Message: ' + str(check_result.message.content) + '\n' +
                                '    Follow time mult.: ' + str(check_result.multipliers.follow_time) + '\n' +
                                '    First time chatter mult.: ' + str(check_result.multipliers.first_time_chatter))

    async def event_message(self, message):
        # Ignore the bots own messages
        if message.echo:
            return

        # nxt = ['nxt', 'Nxt', 'Nxt__1']
        # if any(x in message.content for x in nxt):
        #     module_logger.info('Protest')
        #     await message.channel.send('Nxt is on a strike to protest against Deathy.')

        # Check the message and handle the result
        spam_bot_result = await self.spam_bot_filter.check_message(message)
        await self.handle_check_result(spam_bot_result)

        if self.gamble_bot.gambles_remaining.value > 0:
            gamble_result = self.gamble_bot.parse_message(message)
            if gamble_result:
                self.gamble_bot.result_q.put_nowait(gamble_result)

        # Send notifications for specific message keywords
        self.notifier.check_message(message)

        # Since we have commands and are overriding the default `event_message`
        # We must let the bot know we want to handle and invoke our commands...
        await self.handle_commands(message)

    async def say(self, channel_name: str, message: str):
        channel = self.get_channel(channel_name)
        try:
            await channel.send(message)
        except AttributeError:
            module_logger.error('Channel ' + str(channel_name) + ' not found, make sure the bot has joined the '
                                                                 'channel')

# TODO: monitor for untimeout events while waiting to ban someone
# TODO: Rework the timed ban thing to check the database for user to be banned on a set interval
# TODO: Check if whispers can be used for commands
