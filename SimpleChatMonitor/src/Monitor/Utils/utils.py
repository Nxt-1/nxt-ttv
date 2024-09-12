import argparse
import logging
import multiprocessing
import sys
from pathlib import Path
from typing import Dict, List

module_logger = logging.getLogger(__name__)


def check_folder(folder: str, use_logging: bool) -> None:
    """
    Helper function that ensures a folder exist or can be created.

    :param folder: The path to the folder
    :param use_logging: Logging module will be used if True, otherwise output will be placed on stdout/stderr
    :raises FileNotFoundError if a parent folder does not exist.
    :raises PermissionError if lacking write permissions
    """
    try:
        if use_logging:
            module_logger.debug('Checking folder: ' + folder)
        else:
            sys.stdout.write('Checking folder: ' + folder + '\n')
        Path(folder).mkdir(parents=False, exist_ok=True)
    except FileNotFoundError as e:
        if use_logging:
            module_logger.error('Parent folder for \'' + folder + '\' does not exist: ' + str(e))
        else:
            sys.stderr.write('Parent folder for \'' + folder + '\' does not exist: ' + str(e) + '\n')
        raise FileNotFoundError
    except PermissionError as e:
        if use_logging:
            module_logger.error('Cannot create \'' + folder + '\', permission denied: ' + str(e))
        else:
            sys.stderr.write('Cannot create \'' + folder + '\', permission denied: ' + str(e) + '\n')
        raise PermissionError


def setup_arg_parser() -> argparse.ArgumentParser():
    """
    Helper function to create and add all arguments to a commandline argument parser

    :return: The parser object
    """

    parser = argparse.ArgumentParser()

    parser.add_argument('-t', '--token', type=str, required=True, help='Bot channel\'s own OAth token')
    parser.add_argument('-i', '--own_id', type=int, required=True, help='Twitch ID of the bot')
    parser.add_argument('-ci', '--client_id', type=str, required=True, help='Client ID for the event sub of the bot')
    parser.add_argument('-cs', '--client_secret', type=str, required=True,
                        help='Client secret for the event sub of the bot')

    return parser


class GlobalTerminator(multiprocessing.Process):
    """
    A normal sys.exit() does not work with processes blocking the main thread.

    A single instance of this class is created in __main__ and passed to every process in the program. Instead of
    calling sys.exit(e), do_terminate(e) can be called to shut all the processes and the gui down. In turn all the
    processes need to be passed that instance and check for instance.is_term.is_set() in their run method.
    """

    def __init__(self, from_process_pipe: multiprocessing.Pipe, process_pipe: multiprocessing.Pipe):
        multiprocessing.Process.__init__(self)
        self.is_term = multiprocessing.Event()
        self.exit_code = multiprocessing.Value('i', 0)

        self.__from_process_pipe = from_process_pipe  # The pipe that this class uses to receive from the processes
        self.process_pipe = process_pipe  # This is the pipe that the processes use

    def run(self):
        while not self.is_term.is_set():
            try:
                exit_code = self.__from_process_pipe.recv()
                module_logger.info('Received exit code: ' + str(exit_code))
            except EOFError:
                break
            except KeyboardInterrupt:
                break
            else:
                module_logger.warning('Shutting down the system')
                self.is_term.set()
                self.exit_code.value = exit_code

    def do_terminate(self, exit_code: int) -> None:
        """
        Terminated all the processes that listen and updated the exit_code so the main process exits with the intended
        exit code.

        :param exit_code: The exit code for the main process
        """

        # TODO: This method can no long be used?
        module_logger.warning('Sending system terminate with code ' + str(exit_code) + '\n')
        self.process_pipe.send(exit_code)


class JoinChannel:
    def __init__(self, name: str, twitch_id: int, token: str = None, enable_raffle_module: bool = False):
        self.name = name
        self.twitch_id = twitch_id
        self.token = token
        self.enable_raffle_module = enable_raffle_module


class JoinChannels:
    def __init__(self):
        self.channels: Dict[str, JoinChannel] = {}

    def append_channel(self, channel: JoinChannel):
        self.channels[channel.name] = channel

    def get_channel_name_list(self) -> List[str]:
        return list(self.channels.keys())
