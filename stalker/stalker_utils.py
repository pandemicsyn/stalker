import os
import pwd
import sys
import atexit
import logging
from time import sleep
from signal import SIGTERM
from ConfigParser import ConfigParser, RawConfigParser
from logging.handlers import TimedRotatingFileHandler

def get_logger(name, log_path='/var/log/stalker.log', level=logging.INFO,
               count=7):
    logger = logging.getLogger(name)
    handler = TimedRotatingFileHandler(log_path, when='midnight',
                                       backupCount=count)
    formatter = logging.Formatter('%(name)s: %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger

class FileLikeLogger(object):

    def __init__(self, logger):
        self.logger = logger

    def write(self, message):
        self.logger.info(message)


class Daemon:
    """
    A generic daemon class.

    Usage: subclass the Daemon class and override the run() method
    """

    def __init__(self, pidfile, stdin='/dev/null', stdout='/dev/null',
                 stderr='/dev/null'):
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr
        self.pidfile = pidfile

    def daemonize(self):
        """
        do the UNIX double-fork magic, see Stevens' "Advanced
        Programming in the UNIX Environment" for details (ISBN 0201563177)
        http://www.erlenstar.demon.co.uk/unix/faq_2.html#SEC16
        """
        try:
            pid = os.fork()
            if pid > 0:
                # exit first parent
                sys.exit(0)
        except OSError, err:
            sys.stderr.write("fork #1 failed: %d (%s)\n" %
                             (err.errno, err.strerror))
            sys.exit(1)

        # decouple from parent environment
        os.chdir("/")
        os.setsid()
        os.umask(0)

        # do second fork
        try:
            pid = os.fork()
            if pid > 0:
                # exit from second parent
                sys.exit(0)
        except OSError, err:
            sys.stderr.write("fork #2 failed: %d (%s)\n" %
                             (err.errno, err.strerror))
            sys.exit(1)

        # redirect standard file descriptors
        sys.stdout.flush()
        sys.stderr.flush()
        stin = file(self.stdin, 'r')
        stout = file(self.stdout, 'a+')
        sterr = file(self.stderr, 'a+', 0)
        os.dup2(stin.fileno(), sys.stdin.fileno())
        os.dup2(stout.fileno(), sys.stdout.fileno())
        os.dup2(sterr.fileno(), sys.stderr.fileno())

        # write pidfile
        atexit.register(self.delpid)
        pid = str(os.getpid())
        file(self.pidfile, 'w+').write("%s\n" % pid)

    def delpid(self):
        """Remove pid file"""
        os.remove(self.pidfile)

    def start(self, *args, **kw):
        """
        Start the daemon
        """
        # Check for a pidfile to see if the daemon already runs
        try:
            pidfile = file(self.pidfile, 'r')
            pid = int(pidfile.read().strip())
            pidfile.close()
        except IOError:
            pid = None
        if pid:
            message = "pidfile %s already exist. Daemon already running?\n"
            sys.stderr.write(message % self.pidfile)
            sys.exit(1)
        # Start the daemon
        self.daemonize()
        self.run(*args, **kw)

    def stop(self):
        """
        Stop the daemon
        """
        # Get the pid from the pidfile
        try:
            pidfile = file(self.pidfile, 'r')
            pid = int(pidfile.read().strip())
            pidfile.close()
        except IOError:
            pid = None
        if not pid:
            message = "pidfile %s does not exist. Daemon not running?\n"
            sys.stderr.write(message % self.pidfile)
            return  # not an error in a restart
        try:
            while 1:
                os.kill(pid, SIGTERM)
                sleep(0.1)
        except OSError, err:
            err = str(err)
            if err.find("No such process") > 0:
                if os.path.exists(self.pidfile):
                    os.remove(self.pidfile)
            else:
                print str(err)
                sys.exit(1)

    def restart(self, *args, **kw):
        """Restart the daemon"""
        self.stop()
        self.start(*args, **kw)

# stolen from swfit.common.utils


def readconf(conffile, section_name=None, log_name=None, defaults=None,
             raw=False):
    """
    Read config file and return config items as a dict

    :param conffile: path to config file, or a file-like object (hasattr
                     readline)
    :param section_name: config section to read (will return all sections if
                     not defined)
    :param log_name: name to be used with logging (will use section_name if
                     not defined)
    :param defaults: dict of default values to pre-populate the config with
    :returns: dict of config items
    """
    if defaults is None:
        defaults = {}
    if raw:
        c = RawConfigParser(defaults)
    else:
        c = ConfigParser(defaults)
    if hasattr(conffile, 'readline'):
        c.readfp(conffile)
    else:
        if not c.read(conffile):
            print ("Unable to read config file %s") % conffile
            sys.exit(1)
    if section_name:
        if c.has_section(section_name):
            conf = dict(c.items(section_name))
        else:
            print ("Unable to find %s config section in %s") % \
                  (section_name, conffile)
            sys.exit(1)
        if "log_name" not in conf:
            if log_name is not None:
                conf['log_name'] = log_name
            else:
                conf['log_name'] = section_name
    else:
        conf = {}
        for s in c.sections():
            conf.update({s: dict(c.items(s))})
        if 'log_name' not in conf:
            conf['log_name'] = log_name
    conf['__file__'] = conffile
    return conf
