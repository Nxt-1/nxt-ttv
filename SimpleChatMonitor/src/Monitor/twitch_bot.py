import logging
import multiprocessing
from typing import Union, Callable, Coroutine, Optional, Dict

import twitchio
from twitchio.ext import commands

from Monitor.twitchbot_functions.gambling import GambleParser
from Monitor.twitchbot_functions.message_filter import MessageChecker, BanEvent, CheckResult, CheckResultType, \
    IgnoreReason
from Monitor.twitchbot_functions.voting import Voter
from Monitor.Utils import constants
from Monitor.Utils.custom_errors import CancelError

module_logger = logging.getLogger(__name__)


class TwitchBot(commands.Bot):
    def __init__(self, token: str, prefix: Union[str, list, tuple, set, Callable, Coroutine], client_secret: str = None,
                 initial_channels: Union[list, tuple, Callable] = None, heartbeat: Optional[float] = 30.0, **kwargs):

        super().__init__(token=token, prefix=prefix, client_secret=client_secret, initial_channels=initial_channels,
                         heartbeat=heartbeat, kwargs=kwargs)
        self.mp_manager = multiprocessing.Manager()
        self.spam_bot_filter = MessageChecker(cyrillics_score=10)
        self.ban_events: Dict[
            str, BanEvent] = {}  # Dict containing all the currently active BanEvents (the author's name is used as key)
        self.gamble_bot = GambleParser('nxthammerboi', self.loop)
        self.break_voter = Voter(self.mp_manager, votes_required=5, vote_period=60, fail_timeout_s=10 * 60,
                                 pass_timeout_s=3 * 60 * 60, double_names={'ninariioforien'},
                                 announce_message='We are voting to make Deathy take 3 minute break. Vote by typing ?votebreak')
        self.balance_start: int = 0  # Starting balance for Arkas's sellout stream

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
                       'world dominion ofcourse.')

    @commands.command()
    async def fp(self, ctx: commands.Context):
        # TODO: Check user roles

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
            self.spam_bot_filter.read_config_file(constants.CONFIG_PATH)
            await ctx.send('Reloaded complete, I feel even more powerful now')

    @commands.command()
    async def votebreak(self, ctx: commands.Context):
        """"
        Handles a user requesting a break vote
        """

        if ctx.channel.name == 'deathy_tv':
            await self.break_voter.add_vote(ctx.message)

    @commands.command()
    async def set_balance(self, ctx: commands.Context):
        """"
        Sets the initial balance for Arkas's sellout streams
        """

        if ctx.channel.name == 'arkas':
            # Check that a balance was passed
            if ctx.prefix + ctx.command.name == ctx.message.content:
                module_logger.info('No balance specified in profit command (' + ctx.message.content + '), ignoring')
                await ctx.send('No balance specified, try ' + ctx.prefix + ctx.command.name + ' <balance>')
                return

            # Extract balance
            self.balance_start = int(ctx.message.content.replace(ctx.prefix + ctx.command.name + ' ', ''))
            await ctx.channel.send('Balance updated to: '+str(self.balance_start))

    @commands.command()
    async def profit(self, ctx: commands.Context):
        """"
        Handles the profit calculation for Arkas's sellout streams
        """

        if ctx.channel.name == 'arkas':
            # Check that a balance was passed
            if ctx.prefix + ctx.command.name == ctx.message.content:
                module_logger.info('No balance specified in profit command (' + ctx.message.content + '), ignoring')
                await ctx.send('No balance specified, try ' + ctx.prefix + ctx.command.name + ' <balance>')
                return

            # Extract balance
            balance = int(ctx.message.content.replace(ctx.prefix + ctx.command.name + ' ', ''))
            await ctx.channel.send('Current profit is: ' + str(balance-self.balance_start))

    def add_ban_event(self, ban_event: BanEvent) -> None:
        """
        Stores a new BanEvent in the system.

        :param ban_event: The ban event to add
        """

        if ban_event.check_result.message.author.display_name in self.ban_events:
            module_logger.warning('User ' + str(ban_event.check_result.message.author.display_name) +
                                  ' is already in the ban events')
        else:
            module_logger.info('Adding new ban event for user ' +
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

    async def do_ban(self, message: twitchio.Message) -> None:
        """
        Executes the user ban and clear the ban event from the system
        """

        module_logger.warning('Executing ban on ' + message.author.display_name)
        await message.channel.send('/ban ' + message.author.display_name)
        self.ban_events.pop(message.author.display_name)

    async def handle_check_result(self, check_result: CheckResult):
        if check_result.result_type == CheckResultType.MATCH:
            module_logger.info('Message from ' + check_result.message.author.display_name + ' with score ' +
                               str(check_result.message_score) + ' got flagged: ' + check_result.message.content)
            # Create a new ban event and start the timer
            ban_event = BanEvent(check_result, self.do_ban(check_result.message))
            await ban_event.start()
            self.add_ban_event(ban_event)

            await check_result.message.channel.send(check_result.message.author.display_name + ' Got flagged by ' +
                                                    check_result.checker_name + ' (Use ?fp ' +
                                                    check_result.message.author.display_name + ' to report a false positive)')

        elif check_result.result_type == CheckResultType.IGNORED:
            # Don't log friendly bot results
            if check_result.ignore_reason == IgnoreReason.FRIENDLY_BOT:
                pass
            else:
                module_logger.info('Message from ' + check_result.message.author.display_name + ' with score ' +
                                   str(check_result.message_score) + ' got a pass (' +
                                   str(check_result.ignore_reason.name) + '): ' + check_result.message.content)
                await check_result.message.channel.send('@' + check_result.message.author.display_name +
                                                        ' You get a pass because: ' +
                                                        str(check_result.ignore_reason.name))

    async def event_message(self, message):
        # Ignore the bots own messages
        if message.echo:
            return

        # Log messages containing 'hammerboi'
        if 'hammerboi' in message.content and message.author.display_name != 'StreamElements':
            module_logger.info('Message to me from ' + str(message.author.name) + ': ' + str(message.content))

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
