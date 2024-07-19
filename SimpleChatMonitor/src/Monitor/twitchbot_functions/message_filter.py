import asyncio
import json
import logging
import os
import re
from datetime import timezone, datetime
from enum import Enum
from typing import Optional, Dict

import twitchio
from typing_extensions import Coroutine

from Monitor.Utils import constants
from Monitor.Utils.custom_errors import CancelError

module_logger = logging.getLogger(__name__)

# TODO: Allow full cyrillic sentence
IGNORED_SET = re.compile(r'[\W_]+')  # Regex to match any alphanumeric character


class CheckResultType(Enum):
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

    The actual result of the check is stored in 'self.result_type'. If the result was IGNORED, the reason will be
    detailed in 'self.ignore_reason'.
    The total score for the message as well as the display name of the user who sent it, are passed as well.
    """

    def __init__(self, checker_name: str, message: twitchio.Message, result_type: CheckResultType = None,
                 ignore_reason: IgnoreReason = None, message_score: float = 0):
        self.checker_name = checker_name  # The name of the MessageChecker that produced this result
        self.message = message  # The twitchio message instance
        self.result_type = result_type  # Type of result
        self.ignore_reason = ignore_reason  # Reason why a match was ignored
        self.message_score = message_score  # Score of the message


class MessageChecker:
    CYRILLIC_RE = re.compile(r'[А-Яа-яЁё]+', re.IGNORECASE)  # Regex to match any cyrillic character

    def __init__(self, joined_channels: Dict[str, str], cyrillics_score: float = None):
        """
        :param joined_channels: Dict of channel/token the bot had joined, used for follow checking
        :param cyrillics_score: Score to add in case any cyrillic character is found in the message, None to
        disable (default)
        """

        self.name = 'default'  # Descriptor for the specific filter
        self.joined_channels = joined_channels
        # Filter
        self.flagged_re: dict[str, re.Pattern] = {}
        self.cyrillics_score = cyrillics_score
        self.min_score = 999  # Minimum score required for a message to be flagged

        # Multipliers
        self.follow_time_days_cutoff = 0  # Cutoff value in days for the following score multiplier
        self.follow_time_multiplier = 1  # Message score gets multiplied by this if the author was following for the cutoff value or less
        self.first_time_chatter_multiplier = 1  # Message score gets multiplied by this if the message was a first time chat

        # Friendly bot names
        self.bot_names = []  # List with names of friendly bots

        # Options
        self.silent_ignore_bots = False
        self.ignore_channel_staff = False
        self.ignore_vip = False
        self.ignore_subscriber = False
        self.ignore_follower = False

        self.read_config_file(constants.FILTER_CONFIG_PATH)

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
            self.first_time_chatter_multiplier = config_json['multipliers']['first_time_chatter_multiplier']
            module_logger.info('Loaded follow-time multiplier ' + str(self.follow_time_multiplier) + ' (' +
                               str(self.follow_time_days_cutoff) + ' days cutoff)')
            module_logger.info('Loaded first time chatter multiplier ' + str(self.first_time_chatter_multiplier))

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
            result.result_type = CheckResultType.ERROR
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
        # Get the user object of the channel the message was sent in
        message_channel = await message.channel.user()

        # Check if the OAth code of the channel is stored
        token = self.joined_channels.get(message_channel.name)

        if token:
            # Check if the chatter user is following the channel user
            follow_event_list = (await message_channel.fetch_channel_followers(token=token, user_id=message_user.id))
            if follow_event_list:
                # If the author is following but for a short time, multiply the score
                if (datetime.now(tz=timezone.utc) - follow_event_list[0].followed_at).days <= \
                        self.follow_time_days_cutoff:
                    result.message_score *= self.follow_time_multiplier
            else:
                # If the author is not following at all, multiply the score too
                result.message_score *= self.follow_time_multiplier

        if message.first:
            # If first time chatter, multiply the score
            result.message_score *= self.first_time_chatter_multiplier
        # </editor-fold>

        if result.message_score >= self.min_score:
            result.result_type = CheckResultType.MATCH
        else:
            result.result_type = CheckResultType.NO_MATCH

        # <editor-fold desc="Ignore checking">
        # Ignore broadcaster/mods if needed
        if self.silent_ignore_bots and message.author.display_name in self.bot_names:
            result.result_type = CheckResultType.IGNORED
            result.ignore_reason = IgnoreReason.FRIENDLY_BOT

        elif self.ignore_channel_staff and (message.author.is_broadcaster or message.author.is_mod):
            if result.result_type == CheckResultType.MATCH:
                result.result_type = CheckResultType.IGNORED
                result.ignore_reason = IgnoreReason.CHANNEL_STAFF

        elif self.ignore_vip and 'vip' in message.author.badges.keys():
            if result.result_type == CheckResultType.MATCH:
                result.result_type = CheckResultType.IGNORED
                result.ignore_reason = IgnoreReason.VIP

        # Ignore subscriber if needed
        elif self.ignore_subscriber and message.author.is_subscriber:
            if result.result_type == CheckResultType.MATCH:
                result.result_type = CheckResultType.IGNORED
                result.ignore_reason = IgnoreReason.SUBSCRIBER

        # Ignore followers if needed
        elif self.ignore_follower and follow_event_list and follow_event_list[0]:
            if result.result_type == CheckResultType.MATCH:
                result.result_type = CheckResultType.IGNORED
                result.ignore_reason = IgnoreReason.FOLLOWER
        # </editor-fold>

        return result


class BanEvent:
    def __init__(self, check_result: CheckResult, ban_method: Coroutine):
        self.check_result = check_result  # The result from the MessageChecker
        self.ban_method = ban_method  # The actual coroutine including parameters that will be executed after the timer is elapsed.
        self.ban_timer: Optional[asyncio.TimerHandle] = None  # Placeholder for the asyncio timer

    async def start(self) -> None:
        """
        Times out the user and start the ban timer. After the time specified in constants.MINUTES_BEFORE_BAN is elapsed,
        the message author will be banned.
        """

        module_logger.info('Started ' + str(constants.MINUTES_BEFORE_BAN) + 'm ban event timer for user ' +
                           str(self.check_result.message.author.display_name))
        self.ban_timer = asyncio.get_running_loop().call_later(constants.MINUTES_BEFORE_BAN * 60, asyncio.create_task,
                                                               self.ban_method)

    async def cancel(self) -> None:
        """
        Cancels the ban timer if it is currently running and not elapsed yet.
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
