import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from enum import Enum
from typing import Union, Callable, Coroutine, Optional, Dict

import twitchio
from twitchio.ext import commands

from Monitor.Utils import constants
from Monitor.Utils.custom_errors import CancelError

module_logger = logging.getLogger(__name__)

# TODO: Allow full cyrillic sentence
# TODO: Log follow time for ban restore
IGNORED_SET = re.compile('[\W_]+')  # Regex to match any alphanumeric character


class MatchResult(Enum):
    MATCH = 1  # Message was matched
    NO_MATCH = 2  # Message was not matched
    IGNORED = 3  # Message was matched but ignored
    ERROR = 4  # No result could be produced


class IgnoreReason(Enum):
    FRIENDLY_BOT = 1
    CHANNEL_STAFF = 2
    VIP = 3
    SUBSCRIBER = 4
    FOLLOWER = 5


class CheckResult:
    """
    Details the result of a MessageChecker run.

    The actual result of the check is stored in 'self.result'. If the result was IGNORED, the reason will be
    detailed in 'self.ignore_reason'.
    The total score for the message as well as the display name of the user who sent it, are passed as well.
    """

    def __init__(self, checker_name: str, message: twitchio.Message, result: MatchResult = None,
                 ignore_reason: IgnoreReason = None, message_score: float = 0):
        self.checker_name = checker_name  # The name of the MessageChecker that produced this result
        self.message = message  # The twitchio message instance
        self.result = result  # Result of the check
        self.ignore_reason = ignore_reason  # Reason why a match was ignored
        self.message_score = message_score  # Score of the message


class MessageChecker:
    CYRILLIC_RE = re.compile(r'[А-Яа-яЁё]+', re.IGNORECASE)  # Regex to match any cyrillic character

    def __init__(self, cyrillics_score: float = None):
        """
        :param cyrillics_score: Score to add in case any cyrillic character is found in the message, None to
        disable (default)
        """

        self.name = 'default'  # Descriptor for the specific filter
        # Filter
        self.flagged_re: dict[str, re.Pattern] = {}
        self.cyrillics_score = cyrillics_score
        self.min_score = 999  # Minimum score required for a message to be flagged

        # Multipliers
        self.follow_time_days_cutoff = 0  # Cutoff value in days for the following score multiplier
        self.follow_time_multiplier = 1  # Message score gets multiplied by this if the author was following for the cutoff value or less

        # Friendly bot names
        self.bot_names = []  # List with names of friendly bots

        # Options
        self.silent_ignore_bots = False
        self.ignore_channel_staff = False
        self.ignore_vip = False
        self.ignore_subscriber = False
        self.ignore_follower = False

        self.read_config_file(constants.CONFIG_PATH)

        module_logger.info('=== ' + self.name + ' filter completed initializing ===')

    def read_config_file(self, file_path: str) -> None:
        """
        Parses the config file containing the filter configuration.

        :param file_path: Path to the config file
        """

        try:
            with open(os.path.abspath(file_path)) as config_file:
                config_json = json.load(config_file)
        except FileNotFoundError as e:
            module_logger.error('Could not find config file at ' + str(os.path.abspath(file_path)) + ': ' + str(e))
            return
        else:
            # Read the ban lists
            for tier in config_json['flaggedTiers']:
                module_logger.info('Tier name: ' + str(tier) + ' containing: ' + str(config_json['flaggedTiers'][tier]))
                if config_json['flaggedTiers'][tier]:
                    self.flagged_re[tier] = re.compile(r'|'.join(config_json['flaggedTiers'][tier]), re.IGNORECASE)
                else:
                    module_logger.warning('Skipping tier with empty list')

            # Read the min score for a message the get flagged
            self.min_score = config_json['minScore']
            module_logger.info('Min score is ' + str(self.min_score))

            # Read multipliers
            self.follow_time_days_cutoff = config_json['multipliers']['follow_time_days_cutoff']
            self.follow_time_multiplier = config_json['multipliers']['follow_time_multiplier']
            module_logger.info('Loaded follow-time multiplier ' + str(self.follow_time_multiplier) + ' (' +
                               str(self.follow_time_days_cutoff) + ' days cutoff)')

            # Friendly bot names
            self.bot_names = config_json['bot_names']
            module_logger.info('Loaded ' + str(self.bot_names) + ' as friendly bots')

            # Read extra options
            self.silent_ignore_bots = config_json['options']['silent_ignore_bots']
            self.ignore_channel_staff = config_json['options']['ignore_channel_staff']
            self.ignore_vip = config_json['options']['ignore_vip']
            self.ignore_subscriber = config_json['options']['ignore_subscriber']
            self.ignore_follower = config_json['options']['ignore_follower']
            module_logger.info('Loaded ignores: ' + str(self.silent_ignore_bots) + '|' + str(self.ignore_channel_staff)
                               + '|' + str(self.ignore_vip) + '|' + str(self.ignore_subscriber) + '|' +
                               str(self.ignore_follower))

            # Read the filter name
            self.name = config_json['name']

    async def check_message(self, message: twitchio.Message) -> CheckResult:
        """
        Check the passed message against the loaded filter configuration. The result of the check will be returned in
        the form of a CheckResult class instance.

        :param message: The message to check
        :return: The CheckResult instance
        """

        result = CheckResult(self.name, message)

        # Check that config file was read and overwrite the default name
        if self.name == 'default':
            module_logger.warning('Message checker did not read config file: check will not be run')
            result.result = MatchResult.ERROR
            return result

        # <editor-fold desc="Message filtering">
        # Filter out spaces and non-alpha numeric characters
        filtered_msg = IGNORED_SET.sub('', message.content)

        result.message_score = 0
        for (tier, tier_re) in self.flagged_re.items():
            match = set(re.findall(tier_re, filtered_msg))
            tier_score = int(tier, base=10) * len(match)
            result.message_score += tier_score
        # Only check for cyrillics if enabled
        if self.cyrillics_score:
            if re.findall(MessageChecker.CYRILLIC_RE, message.content):
                module_logger.warning('Matched cyrillics')
                result.message_score += self.cyrillics_score
        # </editor-fold>

        # <editor-fold desc="Multipliers">
        # Get the user chatter user object
        message_user = await message.author.user()
        # Get the channel user object
        message_channel = await message.channel.user()
        # Check if the chatter user is following the channel user
        follow_event = await message_user.fetch_follow(message_channel)

        if follow_event:
            # If the author is following but for a short time, multiply the score
            if (datetime.now(tz=timezone.utc) - follow_event.followed_at).days <= self.follow_time_days_cutoff:
                result.message_score *= self.follow_time_multiplier
        else:
            # If the author is not following at all, multiply the score to
            result.message_score *= self.follow_time_multiplier
        # </editor-fold>

        if result.message_score >= self.min_score:
            result.result = MatchResult.MATCH
        else:
            result.result = MatchResult.NO_MATCH

        # <editor-fold desc="Ignore checking">
        # Ignore broadcaster/mods if needed
        if self.silent_ignore_bots and message.author in self.bot_names:
            if result.result == MatchResult.MATCH:
                result.result = MatchResult.IGNORED
                result.ignore_reason = IgnoreReason.FRIENDLY_BOT

        elif self.ignore_channel_staff and (message.author.is_broadcaster or message.author.is_mod):
            if result.result == MatchResult.MATCH:
                result.result = MatchResult.IGNORED
                result.ignore_reason = IgnoreReason.CHANNEL_STAFF

        elif self.ignore_vip and 'vip' in message.author.badges.keys():
            if result.result == MatchResult.MATCH:
                result.result = MatchResult.IGNORED
                result.ignore_reason = IgnoreReason.VIP

        # Ignore subscriber if needed
        elif self.ignore_subscriber and message.author.is_subscriber:
            if result.result == MatchResult.MATCH:
                result.result = MatchResult.IGNORED
                result.ignore_reason = IgnoreReason.SUBSCRIBER

        # Ignore followers if needed
        elif self.ignore_follower and follow_event:
            if result.result == MatchResult.MATCH:
                result.result = MatchResult.IGNORED
                result.ignore_reason = IgnoreReason.FOLLOWER
        # </editor-fold>

        return result


class BanEvent:
    def __init__(self, check_result: CheckResult, ban_method: Coroutine):
        self.check_result = check_result  # The result from the MessageChecker
        self.ban_method = ban_method  # The actual coroutine including parameters that will be executed after the timer is elapsed.
        self.ban_timer: Optional[asyncio.TimerHandle] = None  # Placeholder for the asyncio timer
        # TODO: Add 30s warning timer?

    async def start(self) -> None:
        """
        Times out the user and start the ban timer. After the time specified in constants.MINUTES_BEFORE_BAN is elapsed,
        the message author will be banned.
        """

        module_logger.info('Started ' + str(constants.MINUTES_BEFORE_BAN) + 'm ban event timer for user ' +
                           str(self.check_result.message.author.display_name))
        self.ban_timer = asyncio.get_running_loop().call_later(constants.MINUTES_BEFORE_BAN * 60, asyncio.create_task,
                                                               self.ban_method)

        # await self.check_result.message.channel.send('/delete '+str(self.check_result.message.tags['id']))
        await self.check_result.message.channel.send('/timeout ' + str(self.check_result.message.author.display_name) +
                                                     ' ' + str(constants.MINUTES_BEFORE_BAN) + 'm')

    async def cancel(self) -> None:
        """
        Cancels the ban timer if it is currently running and not elapsed yet. After a cancel, the user is also
        untimed-out and unbanned.

        :return: True if the timer was successfully canceled, False otherwise
        """

        if not self.ban_timer:
            raise CancelError('Unable to cancel the ban on ' + str(self.check_result.message.author.display_name) +
                              ': timer not started')
        elif self.ban_timer.cancelled():
            raise CancelError('Unable to cancel the ban on ' + str(self.check_result.message.author.display_name) +
                              ': timer already canceled')
        else:
            module_logger.warning('Canceling ban on ' + str(self.check_result.message.author.display_name))
            # If the method is not closed, an exception is thrown because the method was never awaited
            self.ban_method.close()
            # Cancel the timer as well
            self.ban_timer.cancel()
            await self.check_result.message.channel.send('/untimeout ' +
                                                         str(self.check_result.message.author.display_name))


class MyBot(commands.Bot):
    def __init__(self, token: str, prefix: Union[str, list, tuple, set, Callable, Coroutine], client_secret: str = None,
                 initial_channels: Union[list, tuple, Callable] = None, heartbeat: Optional[float] = 30.0, **kwargs):

        super().__init__(token=token, prefix=prefix, client_secret=client_secret, initial_channels=initial_channels,
                         heartbeat=heartbeat, kwargs=kwargs)

        self.spam_bot_filter = MessageChecker(cyrillics_score=10)
        self.ban_events: Dict[
            str, BanEvent] = {}  # Dict containing all the currently active BanEvents (the author's display name is used as key)

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
            await ctx.send('Reloaded filter config file')

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
        if check_result.result == MatchResult.MATCH:
            module_logger.info('Message from ' + check_result.message.author.display_name + ' with score ' +
                               str(check_result.message_score) + ' got flagged: ' + check_result.message.content)
            # Create a new ban event and start the timer
            ban_event = BanEvent(check_result, self.do_ban(check_result.message))
            await ban_event.start()
            self.add_ban_event(ban_event)

            await check_result.message.channel.send(check_result.message.author.display_name + ' Got flagged by ' +
                                                    check_result.checker_name + ' (Use ?fp ' +
                                                    check_result.message.author.display_name + ' to report a false positive)')

        elif check_result.result == MatchResult.IGNORED:
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
        if 'hammerboi' in message.content:
            module_logger.info('Message to me from ' + str(message.author.name) + ': ' + str(message.content))

        # Check the message and handle the result
        spam_bot_result = await self.spam_bot_filter.check_message(message)
        await self.handle_check_result(spam_bot_result)

        # Since we have commands and are overriding the default `event_message`
        # We must let the bot know we want to handle and invoke our commands...
        await self.handle_commands(message)
