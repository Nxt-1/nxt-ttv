import logging
import sqlite3
from typing import List

from Monitor.Utils import constants

module_logger = logging.getLogger(__name__)
_db_connection: sqlite3.Connection | None = None


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


def execute_query(query: str, query_vars=None) -> None:
    """
    Takes a query and an optional tuple of query variables to execute on the database.
    :param query: Query string to execute
    :param query_vars: Optional tuple of variables in the query string
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
            user_name TEXT,
            channel TEXT,
            message TEXT,
            score INTEGER,
            event_date DATETME,
            is_unbanned BOOL DEFAULT 0,
            is_banned BOOL DEFAULT 0,
            follow_time INTEGER,
            is_near_miss BOOL,
            ignore_reason TEXT DEFAULT 'NONE'
        );
        """
    execute_query(table_query)
    module_logger.debug('Filter table created')

# class Database:
#     def __init__(self, db_path: str):
#         self.db_path = db_path
#         self.connection = None
#
#     def increment_subs(self, gifter_id: int, gifter_name: str, n_subs: int = 1) -> None:
#         """
#         Increments the number of redeems for a particular user by one. If the user the doesn't exist in the database, it
#         is added first.
#         :param gifter_id: The Twitch ID of the chatter to update
#         :param gifter_name: The Twitch name of the chatter to update
#         :param n_subs: (Optional) Number of subs to add (default =1)
#         """
#         update_query = "INSERT INTO users (id, name, subs) VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET subs=subs+?;"
#         update_variables = (gifter_id, gifter_name.lower(), n_subs, n_subs)
#         self.execute_query(update_query, update_variables)
#
#     def increment_bits(self, redeemer_id: int, redeemer_name: str, n_bits: int) -> None:
#         """
#         Increments the number of bits redeemed for a particular user by the amount specified. If the user the doesn't
#         exist in the database, it is added first.
#         :param redeemer_id: The Twitch ID of the chatter to update
#         :param redeemer_name: The Twitch name of the chatter to update
#         :param n_bits: The number of bits to add
#         """
#         update_query = "INSERT INTO users (id, name, bits) VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET bits=bits+?;"
#         update_variables = (redeemer_id, redeemer_name.lower(), n_bits, n_bits)
#         self.execute_query(update_query, update_variables)
#
#     def increment_redeems(self, redeemer_id: int, redeemer_name: str, n_redeems: int = 1) -> None:
#         """
#         Increments the number of redeems for a particular user by one. If the user the doesn't exist in the database, it
#         is added first.
#         :param redeemer_id: The Twitch ID of the chatter to update
#         :param redeemer_name: The Twitch name of the chatter to update
#         :param n_redeems: (Optional) Number of redeems to add (default =1)
#         """
#
#         update_query = "INSERT INTO users (id, name, redeems) VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET " \
#                        "redeems=redeems+?;"
#         update_variables = (redeemer_id, redeemer_name.lower(), n_redeems, n_redeems)
#         self.execute_query(update_query, update_variables)
#
#     def get_counts_from_name(self, chatter_name: str) -> Tuple[int, int, int]:
#         """
#         Reads the counts (subs, bits & redeems) for a particular user in the database.
#         :param chatter_name: The Twitch name of the chatter to check
#         :return: Tuple(subs, bits, redeems)
#         :exception: IndexError when the user could not be found in the database
#         """
#
#         counts_query = "SELECT subs, bits, redeems FROM users WHERE name=?;"
#         query_vars = (chatter_name.lower(),)
#         # This returns a list, containing a tuple with the number of subs, bits & redeems
#         return self.execute_read_query(counts_query, query_vars)[0]
#
#     def calculate_raffle_tickets_from_name(self, chatter_name: str) -> int:
#         """
#         Calculates the number of raffle tickets for a specific user base on the number of gifted subs and bits
#         :param chatter_name: The Twitch name fo the chatter to check
#         :return: The number of raffle tickets
#         """
#
#         (subs, bits, redeems) = self.get_counts_from_name(chatter_name.lower())
#         # Tickets for subs
#         tickets = math.floor(subs / constants.SUBS_PER_TICKET)
#         # Tickets for bits
#         tickets += math.floor(bits / constants.BITS_PER_TICKET)
#
#         return tickets
#
#     def calculate_all_tickets(self) -> Tuple[int, int]:
#         """
#         Checks the entire database and tallies all total tickets and the total number of users with at least one ticket.
#         :return: Tuple (total_users, total_tickets)
#         """
#
#         counts_query = "SELECT subs, bits FROM users"
#         # This returns a list, containing a tuple with the number of subs & bits
#         counts = self.execute_read_query(counts_query)
#         # Note, this is the total users with at least 1 ticket to their name
#         total_users = 0
#         total_tickets = 0
#         for (subs, bits) in counts:
#             # Tickets for subs
#             user_tickets = math.floor(subs / constants.SUBS_PER_TICKET)
#             # Tickets for bits
#             user_tickets += math.floor(bits / constants.BITS_PER_TICKET)
#
#             if user_tickets > 0:
#                 total_users += 1
#                 total_tickets += user_tickets
#
#         return total_users, total_tickets
#
#     def do_raffle(self) -> str:
#         """
#         Pulls one chatters name out of all tickets.
#         All users get pulled from the database and for every ticket a user has, his/her name is added to a list once.
#         Afterwards an entry is pulled from the list at random.
#         :return: The name of the chatter that won the raffle
#         """
#
#         counts_query = "SELECT name, subs, bits FROM users"
#         # This returns a list, containing a tuple with the name, number of subs & bits
#         counts = self.execute_read_query(counts_query)
#
#         # Add all name/tickets to a list
#         raffle_list = []
#         for (name, subs, bits) in counts:
#             # Tickets for subs
#             user_tickets = math.floor(subs / constants.SUBS_PER_TICKET)
#             # Tickets for bits
#             user_tickets += math.floor(bits / constants.BITS_PER_TICKET)
#
#             for n_tickets in range(user_tickets - 1):
#                 raffle_list.append(name)
#
#         # Pull random entry
#         winner = random.choice(raffle_list)
#         module_logger.info(str(winner) + ' won the raffle, he had ' +
#                            str(self.calculate_raffle_tickets_from_name(winner)) + ' tickets in the raffle')
#         return winner
