import asyncio
import logging
import multiprocessing
import re
import sys
import threading
from typing import Optional

import twitchio

module_logger = logging.getLogger(__name__)


class GambleParser:
    MAX_LOSS_FACTOR = 500

    def __init__(self, own_name: str, loop):
        """
        Class that facilitates StreamElements gambling.
        """

        self.loop = loop  # Asyncio eventloop

        # TODO: Calculate this automatically based on a risk percentage
        self.__gamble_base = 1  # Base value to gamble

        self.gambles_remaining = multiprocessing.Value('i', 0)  # Total number of gambles remaining
        self.__gamble_task: Optional[threading.Thread] = None

        self.result_q = asyncio.Queue()

        self.w_preamble = chr(1) + 'ACTION ' + own_name + ' won '  # SE's preamble to a win message
        self.w_all_preamble = chr(
            1) + 'ACTION PogChamp ' + own_name + ' went all in and won '  # SE's preamble to a loss all message
        self.l_preamble = chr(1) + 'ACTION ' + own_name + ' gambled '  # SE's preamble to a loss message
        self.l_all_preamble = chr(
            1) + 'ACTION ' + own_name + ' went all in and lost every single on of their '  # SE's preamble to a loss all message
        self.broke_id = '@' + own_name + ', you only have '

    def start_gamble(self, channel: twitchio.Channel, n_bets: int):
        module_logger.info('Starting ' + str(n_bets) + ' gamble(s) in ' + str(channel.name) + '\'s channel')

        self.gambles_remaining.value = n_bets
        self.__gamble_task = asyncio.create_task(self.gamble_routine(channel))

    async def gamble_routine(self, channel: twitchio.Channel):
        module_logger.info('Starting gamble routine')

        winnings = 0
        # Kickoff the
        await self.send_gamble(channel, self.__gamble_base)

        # Main loop
        bet = 0
        while self.gambles_remaining.value > 0:
            # TODO: Give this a better place
            timeout = 5

            try:
                module_logger.debug('Waiting for the queue, ' + str(self.gambles_remaining.value) +
                                    ' remaining - running total: ' + str(winnings))
                result = await asyncio.wait_for(self.result_q.get(), timeout)
            except asyncio.TimeoutError:
                module_logger.warning('Timed out waiting for gamble result, re-sending in 10s')
                await asyncio.sleep(10)
                await self.send_gamble(channel, bet)
                continue
            else:
                if result == (-sys.maxsize - 1):
                    module_logger.info('Ran out of gamble points, stopping now')
                    with self.gambles_remaining.get_lock():
                        self.gambles_remaining.value = 0
                    continue

                winnings += result
                with self.gambles_remaining.get_lock():
                    self.gambles_remaining.value -= 1

                if self.gambles_remaining.value > 0:
                    if result > 0:
                        bet = self.__gamble_base
                    elif result < self.__gamble_base * GambleParser.MAX_LOSS_FACTOR * -1:
                        module_logger.info('Massive loss, stopping now')
                        with self.gambles_remaining.get_lock():
                            self.gambles_remaining.value = 0
                        continue
                    else:
                        # Normal loss
                        bet = result * -2

                    await self.send_gamble(channel, bet)
                self.result_q.task_done()

        module_logger.info('Gamble routine completed with ' + str(winnings) + ' profit')

    def parse_message(self, message: twitchio.Message) -> Optional[int]:
        """
        Check any message to for a gamble result. Any non-SE messages, as well as results for other users will be
        ignored. The parsed win/loss value will be returned.
            * In case of a win, the return value will be hte amount won.
            * In case of a loss, the return value will be the amount lost as a negative.
            * In case the message was not applicable, the return value is None.
            * In case the message was 'you only have xyz points left', the returns value is -sys.maxsize-1.

        :param message: The message to check
        :return: The gamble net result
        """

        # Ignore non-SE messages
        if message.author.display_name != 'StreamElements':
            return

        message_str = str(message.content)

        if message_str.startswith(self.w_preamble):
            # Start is removed first, then re is used to find the first number and is cast to int
            result = int(re.search(r'\d+', message_str.replace(self.w_preamble, '')).group(), 10)
            return result

        elif message_str.startswith(self.w_all_preamble):
            # Start is removed first, then re is used to find the first number and is cast to int
            result = int(re.search(r'\d+', message_str.replace(self.w_all_preamble, '')).group(), 10)
            return result

        elif message_str.startswith(self.l_preamble):
            # Start is removed first, then re is used to find the first number, cast to int and made negative
            result = int(re.search(r'\d+', message_str.replace(self.l_preamble, '')).group(), 10) * -1
            return result

        elif message_str.startswith(self.l_all_preamble):
            # Start is removed first, then re is used to find the first number, cast to int and made negative
            result = int(re.search(r'\d+', message_str.replace(self.l_all_preamble, '')).group(), 10) * -1
            return result

        elif self.broke_id in message_str:
            return -sys.maxsize - 1

        else:
            return None

    async def send_gamble(self, channel: twitchio.Channel, bet: int):
        await channel.send('!gamble ' + str(bet))
