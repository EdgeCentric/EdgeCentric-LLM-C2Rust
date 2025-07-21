import logging
import logging.handlers
import sys

FORMATTER = logging.Formatter(
    fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


class StreamToLogger(object):
    """
    Fake file-like stream object that redirects writes to a logger instance.
    """

    def __init__(self, logger, log_level=logging.INFO):
        self.terminal = sys.stdout
        self.logger = logger
        self.log_level = log_level
        self.linebuf = ""

    def __getattr__(self, attr):
        try:
            attr_value = getattr(self.terminal, attr)
        except:
            return None
        return attr_value

    def write(self, buf):
        temp_linebuf = self.linebuf + buf
        self.linebuf = ""
        for line in temp_linebuf.splitlines(True):
            # From the io.TextIOWrapper docs:
            #   On output, if newline is None, any '\n' characters written
            #   are translated to the system default line separator.
            # By default sys.stdout.write() expects '\n' newlines and then
            # translates them so this is still cross platform.
            if line[-1] == "\n":
                encoded_message = line.encode("utf-8", "ignore").decode("utf-8")
                self.logger.log(self.log_level, encoded_message.rstrip())
            else:
                self.linebuf += line

    def flush(self):
        if self.linebuf != "":
            encoded_message = self.linebuf.encode("utf-8", "ignore").decode("utf-8")
            self.logger.log(self.log_level, encoded_message.rstrip())
        self.linebuf = ""


# Set the format of root handlers
root_logger = logging.getLogger()

console_handler = logging.StreamHandler()
console_handler.setFormatter(FORMATTER)

# the message printed to console are limited
console_handler.setLevel(logging.INFO)
root_logger.addHandler(console_handler)
# we allow any levels of messages
root_logger.setLevel(logging.DEBUG)


def enable_capture():
    # Redirect stdout and stderr to loggers
    if not isinstance(sys.stdout, StreamToLogger):
        stdout_logger = logging.getLogger("stdout")
        stdout_logger.setLevel(logging.DEBUG)
        sl = StreamToLogger(stdout_logger, logging.INFO)
        sys.stdout = sl

    if not isinstance(sys.stderr, StreamToLogger):
        stderr_logger = logging.getLogger("stderr")
        stderr_logger.setLevel(logging.ERROR)
        sl = StreamToLogger(stderr_logger, logging.ERROR)
        sys.stderr = sl


def disable_capture():
    # Restore stdout and stderr to their original state
    if isinstance(sys.stdout, StreamToLogger):
        sys.stdout.flush()
        sys.stdout = sys.stdout.terminal

    if isinstance(sys.stderr, StreamToLogger):
        sys.stderr.flush()
        sys.stderr = sys.stderr.terminal


logging.getLogger("httpx").setLevel(logging.WARNING)
