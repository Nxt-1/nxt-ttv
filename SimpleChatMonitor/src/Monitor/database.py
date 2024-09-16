import logging
import math
import random
import sqlite3
from enum import Enum
from typing import List, Tuple

from Monitor.Utils import constants

module_logger = logging.getLogger(__name__)
_db_connection: sqlite3.Connection | None = None


class FilterEventStatus(Enum):
    NOOP = 1  # The event is registered but required further action
    TIMED = 2  # The event timed the user out and is currently in the grace period, awaiting a ban
    UNBANNED = 3  # During the grace period a mod unbanned the user and should not continue to be banned
    BANNED = 4  # The event is finished with a user banned either by the bot or by an eager mod, during the grace period


# https://stackoverflow.com/questions/6829675/the-proper-method-for-making-a-db-connection-available-across-many-python-module
def get_connection() -> sqlite3.Connection:
    global _db_connection
    if not _db_connection:
        try:
            _db_connection = sqlite3.connect(constants.DATABASE_PATH)
            module_logger.info('Connected to SQLite database')
        except sqlite3.Error as e:
            module_logger.critical('Failed to connect to database: ' + str(e))

    return _db_connection


# __all__ = ['get_connection']


def execute_query(query: str, query_vars=None) -> sqlite3.Cursor:
    """
    Takes a query and an optional tuple of query variables to execute on the database.
    :param query: Query string to execute
    :param query_vars: Optional tuple of variables in the query string
    :returns the database cursor
    """

    cursor = _db_connection.cursor()
    try:
        if query_vars:
            cursor.execute(query, query_vars)
        else:
            cursor.execute(query)
        _db_connection.commit()
        module_logger.debug('Query success')
    except sqlite3.Error as e:
        module_logger.error('Query failed: ' + str(e))

    return cursor


def execute_read_query(query: str, query_vars=None) -> List:
    """
    Takes a query and an optional tuple of query variables to execute and read from the database.
    :param query: Query string to execute
    :param query_vars: Optional tuple of variables in the query string
    :return: A list containing the read result
    """

    cursor = _db_connection.cursor()
    try:
        if query_vars:
            cursor.execute(query, query_vars)
        else:
            cursor.execute(query)
        result = cursor.fetchall()
        return result
    except sqlite3.Error as e:
        module_logger.error('Query failed: ' + str(e))


def create_filter_table() -> None:
    """
    Creates the required table for the message filter functionality if it does not exist. If exist already, this call is
    silently ignored.
    """

    module_logger.debug('Creating filter table')
    table_query = """
        CREATE TABLE IF NOT EXISTS FilterEvents (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            channel TEXT,
            message TEXT,
            score INTEGER,
            follow_time INTEGER,
            event_date DATETME DEFAULT CURRENT_TIMESTAMP,
            status TEXT,
            is_near_miss BOOL,
            ignore_reason TEXT
        );
        """
    execute_query(table_query)
    module_logger.debug('Filter table created')


def insert_new_event(user_id: int, username: str, channel: str, message: str, score: int, follow_time: int,
                     status: FilterEventStatus, is_near_miss: bool, ignore_reason: str) -> None:
    """
    Adds a new basic filter event to the database.
    :param user_id: The user id of twitch user that triggered the event
    :param username: The username of the twitch user that triggered the event
    :param channel: The channel name of the channel the event took place in
    :param message: The message that triggered the event
    :param score: The score corresponding with the message
    :param follow_time: The time in days the user was followed for at the time of the event
    :param status: Current status of the event: can be any of NOOP, TIMED, UNBANNED, BANNED
    :param is_near_miss: Boolean indicating if the event was classified as a near miss
    :param ignore_reason: If the message was ignored for some reason, the reason is stored here
    """

    module_logger.debug('Inserting new event')
    query = "INSERT INTO FilterEvents (user_id, username, channel, message, score, follow_time, " \
            " status, is_near_miss, ignore_reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);"
    values = (user_id, username, channel, message, score, follow_time, status.name, is_near_miss, ignore_reason)
    execute_query(query, values)


def check_exists(user_id: int) -> bool:
    """
    Checks whether a filter event with a specific user_id exists in the database.
    :param user_id: The user_id corresponding to the event to check
    :return: boolean indicating if the event can be found in the database
    """

    module_logger.debug('Checking existence of user id ' + str(user_id))
    query = "SELECT EXISTS(SELECT 1 FROM FilterEvents WHERE user_id = ?);"
    values = (user_id,)
    cursor = execute_query(query, values)
    if cursor.fetchone() == (1,):
        module_logger.debug('User id ' + str(user_id) + ' exists in the database')
        return True
    else:
        module_logger.debug('User id ' + str(user_id) + ' does not exist in the database')
        return False


def update_status(user_id: int, status: FilterEventStatus) -> None:
    """
    Updates the status field. The user id should already exist in the database.

    :param user_id: The id of the user to update
    :param status: The new status
    """

    module_logger.debug('Setting user id ' + str(user_id) + ' to ' + str(status.name))
    if check_exists(int(user_id)):
        query = "UPDATE FilterEvents SET status = ? WHERE user_id = ?;"
        values = (status.name, user_id)
        execute_query(query, values)
    else:
        module_logger.debug('User id does not exist in the database, ignoring the update')


def create_raffle_table() -> None:
    """
    Creates the required table for the raffle functionality if it does not exist. If exist already, this call is
    silently ignored.
    """

    module_logger.debug('Creating raffle table')
    table_query = """
        CREATE TABLE IF NOT EXISTS RaffleUsers (
            user_id INTEGER,
            username TEXT,
            channel_id INTEGER,
            subs INTEGER DEFAULT 0,
            bits INTEGER DEFAULT 0,
            redeems INTEGER DEFAULT 0,
            PRIMARY KEY(user_id, channel_id)
        );
        """
    execute_query(table_query)
    module_logger.debug('Raffle table created')


def increment_subs(gifter_id: int, gifter_name: str, channel_id: int, n_subs: int = 1) -> None:
    """
    Increments the number of redeems for a particular user by one. If the user the doesn't exist in the database, it
    is added first.

    :param gifter_id: The Twitch ID of the chatter to update
    :param gifter_name: The Twitch name of the chatter to update
    :param channel_id: The Twitch ID of the broadcaster channel
    :param n_subs: (Optional) Number of subs to add (default =1)
    """

    update_query = "INSERT INTO RaffleUsers (user_id, username, channel_id, subs) VALUES (?, ?, ?, ?)" \
                   " ON CONFLICT(user_id, channel_id) DO UPDATE SET subs=subs+?;"
    update_variables = (gifter_id, gifter_name.lower(), channel_id, n_subs, n_subs)
    execute_query(update_query, update_variables)


def increment_bits(redeemer_id: int, redeemer_name: str, channel_id: int, n_bits: int) -> None:
    """
    Increments the number of bits redeemed for a particular user by the amount specified. If the user the doesn't
    exist in the database, it is added first.
    :param redeemer_id: The Twitch ID of the chatter to update
    :param redeemer_name: The Twitch name of the chatter to update
    :param channel_id: The Twitch ID of the broadcaster channel
    :param n_bits: The number of bits to add
    """

    update_query = "INSERT INTO RaffleUsers (user_id, username, channel_id, bits) VALUES (?, ?, ?, ?) " \
                   "ON CONFLICT(user_id, channel_id) DO UPDATE SET bits=bits+?;"
    update_variables = (redeemer_id, redeemer_name.lower(), channel_id, n_bits, n_bits)
    execute_query(update_query, update_variables)


def increment_redeems(redeemer_id: int, redeemer_name: str, channel_id: int, n_redeems: int = 1) -> None:
    """
    Increments the number of redeems for a particular user by one. If the user the doesn't exist in the database, it
    is added first.
    :param redeemer_id: The Twitch ID of the chatter to update
    :param redeemer_name: The Twitch name of the chatter to update
    :param channel_id: The Twitch ID of the broadcaster channel
    :param n_redeems: (Optional) Number of redeems to add (default =1)
    """

    update_query = "INSERT INTO RaffleUsers (user_id, username, channel_id, redeems) VALUES (?, ?, ?, ?) " \
                   "ON CONFLICT(user_id, channel_id) DO UPDATE SET redeems=redeems+?;"
    update_variables = (redeemer_id, redeemer_name.lower(), channel_id, n_redeems, n_redeems)
    execute_query(update_query, update_variables)


def get_counts_from_name(chatter_name: str, channel_id: int) -> Tuple[int, int, int]:
    """
    Reads the counts (subs, bits & redeems) for a particular user in the database.
    :param chatter_name: The Twitch name of the chatter to check
    :param channel_id: The Twitch ID of the broadcaster channel
    :return: Tuple(subs, bits, redeems)
    :exception: IndexError when the user could not be found in the database
    """

    counts_query = "SELECT subs, bits, redeems FROM RaffleUsers WHERE username = ? AND channel_id = ?;"
    query_vars = (chatter_name.lower(), channel_id)
    # This returns a list, containing a tuple with the number of subs, bits & redeems
    return execute_read_query(counts_query, query_vars)[0]


def calculate_raffle_tickets_from_name(chatter_name: str, channel_id: int) -> int:
    """
    Calculates the number of raffle tickets for a specific user base on the number of gifted subs and bits
    :param chatter_name: The Twitch name fo the chatter to check
    :param channel_id: The Twitch ID of the broadcaster channel
    :return: The number of raffle tickets
    """

    (subs, bits, redeems) = get_counts_from_name(chatter_name.lower(), channel_id)
    # Tickets for subs
    tickets = math.floor(subs / constants.SUBS_PER_TICKET)
    # Tickets for bits
    tickets += math.floor(bits / constants.BITS_PER_TICKET)

    return tickets


def calculate_all_tickets(channel_id: int) -> Tuple[int, int]:
    """
    Checks the entire database and tallies all total tickets and the total number of users with at least one ticket.
    :param channel_id: The Twitch ID of the broadcaster channel
    :return: Tuple (total_users, total_tickets)
    """

    counts_query = "SELECT subs, bits FROM RaffleUsers WHERE channel_id = ?"
    query_vars = (channel_id, )
    # This returns a list, containing a tuple with the number of subs & bits
    counts = execute_read_query(counts_query, query_vars)
    # Note, this is the total users with at least 1 ticket to their name
    total_users = 0
    total_tickets = 0
    for (subs, bits) in counts:
        # Tickets for subs
        user_tickets = math.floor(subs / constants.SUBS_PER_TICKET)
        # Tickets for bits
        user_tickets += math.floor(bits / constants.BITS_PER_TICKET)

        if user_tickets > 0:
            total_users += 1
            total_tickets += user_tickets

    return total_users, total_tickets


def do_raffle(channel_id: int) -> str:
    """
    Pulls one chatters name out of all tickets.
    All users get pulled from the database and for every ticket a user has, his/her name is added to a list once.
    Afterwards an entry is pulled from the list at random.
    :param channel_id: The Twitch ID of the broadcaster channel
    :return: The name of the chatter that won the raffle
    """

    counts_query = "SELECT name, subs, bits FROM RaffleUsers WHERE channel_id = ?"
    query_vars = (channel_id,)
    # This returns a list, containing a tuple with the name, number of subs & bits
    counts = execute_read_query(counts_query, query_vars)

    # Add all name/tickets to a list
    raffle_list = []
    for (name, subs, bits) in counts:
        # Tickets for subs
        user_tickets = math.floor(subs / constants.SUBS_PER_TICKET)
        # Tickets for bits
        user_tickets += math.floor(bits / constants.BITS_PER_TICKET)

        for n_tickets in range(user_tickets - 1):
            raffle_list.append(name)

    # Pull random entry
    winner = random.choice(raffle_list)
    module_logger.info(str(winner) + ' won the raffle, he had ' +
                       str(calculate_raffle_tickets_from_name(winner, channel_id)) + ' tickets in the raffle')
    return winner
