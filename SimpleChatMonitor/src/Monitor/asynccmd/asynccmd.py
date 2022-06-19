import asyncio
import logging
import string
import sys
from contextlib import suppress

module_logger = logging.getLogger(__name__)


class Cmd:
    """
    TODO: need documentation
    TODO: need to review
    TODO: need to refactor in doc like ->
    TODO: need to refactor protected methods
    Reader not supported in Win32

    """
    loop = None  # asyncio.get_even_loop()
    mode = "Reader"  # Reader:loop.add_reader OR Run:loop.run_in_executor
    run_loop = False  # True: loop.run_forever OR False: no run event loop
    prompt = "asynccmd > "  # Str: it would writen before input
    intro = "asynccmd ready to serve"  # Str: intro message before cli start
    currentcmd = ""  # Str: currentcmd that catch
    lastcmd = ""  # Str: last cmd command
    allowedchars = string.ascii_letters + string.digits + '_'
    stdin = sys.stdin
    stdout = sys.stdout

    #
    # CMD command section
    #

    @staticmethod
    def do_test(arg):
        module_logger.cmd("Called build-in function do_test with args:" + arg)

    def do_help(self, arg):
        module_logger.cmd("Default help handler. Have arg :" + arg + ", but ignore its.")
        module_logger.cmd("Available command list: ")
        for i in dir(self.__class__):
            if i.startswith("do_"):
                module_logger.cmd(" - " + i[3:])

    def do_exit(self, arg):
        module_logger.cmd("Rescue exit!!")
        raise KeyboardInterrupt

    #
    # Cmd section
    #

    def __init__(self, mode="Reader", run_loop=False):
        self.mode = mode
        self.run_loop = run_loop

    def cmdloop(self, loop=None):
        self._start_controller(loop)

    def _start_controller(self, loop):
        """
        Control structure to start new cmd
        :param loop: event loop
        :return: None
        """
        # Loop check
        if loop is None:
            if sys.platform == 'win32':
                self.loop = asyncio.ProactorEventLoop()
            else:
                self.loop = asyncio.get_event_loop()
        else:
            self.loop = loop
        # Starting by add "tasks" in "loop"
        if self.mode == "Reader":
            self._start_reader()
        elif self.mode == "Run":
            self._start_run()
        else:
            raise TypeError("self.mode is not Reader or Run.")
        # Start or not loop.run_forever
        if self.run_loop:
            try:
                module_logger.cmd("Cmd._start_controller start loop inside Cmd object!")
                self.stdout.flush()
                self.loop.run_forever()
            except KeyboardInterrupt:
                module_logger.cmd("Cmd._start_controller stop loop. Bye.")
                self.loop.stop()
                pending = asyncio.all_tasks(loop=self.loop)
                module_logger.cmd(pending)
                for task in pending:
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        self.loop.run_until_complete(task)
                # self.loop.close()

    def _start_run(self):
        if self.loop is None:
            raise TypeError("self.loop is None.")
        self.loop.create_task(self._read_line())
        self.loop.create_task(self._greeting())

    def _start_reader(self):
        if self.loop is None:
            raise TypeError("self.loop is None.")
        self.loop.add_reader(self.stdin.fileno(), self.reader)
        self.loop.create_task(self._greeting())

    def reader(self):
        line = sys.stdin.readline()
        self._exec_cmd(line)
        sys.stdout.write(self.prompt)
        sys.stdout.flush()

    async def _read_line(self):
        await asyncio.sleep(0.1)
        while True:
            line = await self.loop.run_in_executor(None, sys.stdin.readline)
            sys.stdout.flush()
            self._exec_cmd(line)
            module_logger.cmd(self.prompt)
            sys.stdout.flush()

    #
    # Additional methods for work with input
    #

    def _exec_cmd(self, line):
        command, arg, line = self.parseline(line=line)
        if not line:
            return self._emptyline(line)
        if command is None:
            return self._default(line)
        self.lastcmd = line
        if line == 'EOF':
            self.lastcmd = ''
        if command == '':
            return self._default(line)
        else:
            try:
                func = getattr(self, 'do_' + command)
            except AttributeError:
                return self._default(line)
            except KeyboardInterrupt:
                return func(arg)
            return func(arg)

    def parseline(self, line):
        line = line.strip()
        if not line:
            return None, None, line
        elif line[0] == '?':
            line = 'help ' + line[1:]
        elif line[0] == '!':
            if hasattr(self, 'do_shell'):
                line = 'shell ' + line[1:]
            else:
                return None, None, line
        iline, nline = 0, len(line)
        while iline < nline and line[iline] in self.allowedchars:
            iline += 1
        command = line[:iline]
        arg = line[iline:].strip()
        return command, arg, line

    @staticmethod
    def _default(line):
        module_logger.cmd("Invalid command: " + line)

    async def _greeting(self):
        module_logger.cmd(self.intro)
        self.stdout.write(self.prompt)
        self.stdout.flush()

    def _emptyline(self, line):
        """
        handler for empty line if entered.
        :param line: this is unused arg (TODO: remove)
        :return: None
        """
        if self.lastcmd:
            module_logger.cmd("Empty line. Try to repeat last command." + line)
            self._exec_cmd(self.lastcmd)
            return
        else:
            module_logger.cmd("Empty line. Nothing happen." + line)
            return
