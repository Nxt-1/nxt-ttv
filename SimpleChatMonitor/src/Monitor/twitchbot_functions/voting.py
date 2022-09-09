import asyncio
import logging
import math
import multiprocessing
from typing import Set, Dict, Optional

import twitchio

module_logger = logging.getLogger(__name__)


class Voter:
    def __init__(self, mp_manager: multiprocessing.Manager(), votes_required: int, vote_period: int,
                 fail_timeout_s: int, pass_timeout_s: int, double_names: Set[str], announce_message: str):
        self.mp_manager = mp_manager  # Reference to a Manager to use in the list
        self.voters: Dict[str, None] = mp_manager.dict()  # Dict (used as set) of all chatter names who already voted
        self.votes_required = votes_required  # Number of votes required to pass
        self.vote_period = vote_period  # Time in seconds before the vote-count is reset
        self.fail_timeout_s = fail_timeout_s  # Time in seconds between failed vote rounds
        self.pass_timeout_s = pass_timeout_s  # Time in seconds between passed vote rounds
        self.double_names = double_names  # Set of chatter names whose vote's count double

        module_logger.info('Voter added with ' + str(self.votes_required) + ' required votes in ' +
                           str(self.vote_period) + 's, timout: ' + str(self.fail_timeout_s) + '|' +
                           str(self.pass_timeout_s))

        self.announce_message = announce_message  # Message that will be announced at the start of a new gamble
        self.vote_open = multiprocessing.Event()  # Indicator that shows if a voting in open or can be started
        self.voting_enable()  # Open the votes on startup

        self.vote_end_coro = None  # Reference to the end_vote coroutine, so it can be canceled properly, will be filled by self.add_vote
        self.vote_end_timer = None  # End timer for the current vote session, will be filled by self.add_vote
        self.vote_timeout_timer = None  # Timeout timer between vote sessions, will be filled by self.voting_end

    async def add_vote(self, chatter_message: twitchio.Message):
        if self.vote_open.is_set():
            n_votes_pre = len(self.voters.keys())
            self.voters.update({chatter_message.author.display_name: None})
            # Some names count double
            if chatter_message.author.display_name in self.double_names:
                module_logger.debug('Double vote added for: ' + chatter_message.author.display_name)
                self.voters.update({chatter_message.author.display_name + '_2': None})
            n_votes_post = len(self.voters.keys())
            if n_votes_post > n_votes_pre:
                # Do some stuff for new vote rounds
                if n_votes_pre == 0:
                    # Start the vote end timer
                    self.vote_end_coro = self.voting_end(chatter_message.channel, self.fail_timeout_s)
                    self.vote_end_timer = asyncio.get_running_loop().call_later(self.vote_period, asyncio.create_task,
                                                                                self.vote_end_coro)
                    # Let the chatter know the vote registered
                    await chatter_message.channel.send(str(chatter_message.author.display_name) +
                                                       ' Started a new vote. You have ' + str(self.vote_period) +
                                                       's to get ' + str(self.votes_required - n_votes_post) +
                                                       ' more votes')
                    module_logger.info('New vote started (' + str(n_votes_post) + '/' + str(self.votes_required) +
                                       ') by ' + chatter_message.author.display_name)
                    await chatter_message.channel.send('/announce ' + self.announce_message)
                else:
                    # Let the chatter know the vote registered
                    await chatter_message.channel.send(str(chatter_message.author.display_name) +
                                                       ' Your vote was registered. (' + str(len(self.voters.keys())) +
                                                       '/' + str(self.votes_required) + ')')
                    module_logger.info('Vote added (' + str(n_votes_post) + '/' + str(self.votes_required) + ') by ' +
                                       chatter_message.author.display_name)
            else:
                pass
                # Ignore double votes

            if n_votes_post >= self.votes_required:
                # If the method is not closed, an exception is thrown because the method was never awaited
                self.vote_end_coro.close()
                # Cancel the timer as well
                self.vote_end_timer.cancel()
                await self.voting_end(chatter_message.channel, self.pass_timeout_s)
        else:
            timeout_remaining_s = self.vote_timeout_timer.when() - asyncio.get_running_loop().time()
            module_logger.debug('Voting will open again in ' + str(int(timeout_remaining_s)) + ' seconds')
            await chatter_message.channel.send('Voting will open again in ' +
                                               str(int(math.ceil(timeout_remaining_s / 60))) + ' min')

    def voting_enable(self):
        """
        Enables a new voting round to start
        """

        # Clear the old votes
        self.voters.clear()
        # Allow new votes
        self.vote_open.set()
        module_logger.debug('Enabled votes')

    async def voting_end(self, channel: Optional[twitchio.Channel], timeout_s: int):
        """
        Handles the end of a voting, either because the allowed time elapsed, or the vote passed.

        :param channel: The channel to send messages in
        :param timeout_s: The time in second before the vote will be opened again
        """

        # Close the voting
        self.vote_open.clear()

        # Check the vote result
        if len(self.voters.keys()) >= self.votes_required:
            await channel.send('Vote passed!')
            module_logger.info('Vote passed')
        else:
            await channel.send('Vote failed, only ' + str(len(self.voters.keys())) + ' out of ' +
                               str(self.votes_required))
            module_logger.info('Vote failed (' + str(len(self.voters.keys())) + '/' + str(self.votes_required) + ')')

        # Start a timer to re-open the voting
        self.vote_timeout_timer = asyncio.get_running_loop().call_later(timeout_s, self.voting_enable)
