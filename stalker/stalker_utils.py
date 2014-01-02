import os
import pwd
import sys
import errno
import atexit
import logging
from sys import maxint
from time import sleep
from signal import SIGTERM
from ConfigParser import ConfigParser, RawConfigParser

import eventlet
from eventlet.green import socket, threading

import time

# logging doesn't import patched as cleanly as one would like
from logging.handlers import SysLogHandler, TimedRotatingFileHandler
import logging
logging.thread = eventlet.green.thread
logging.threading = eventlet.green.threading
logging._lock = logging.threading.RLock()
# setup notice level logging
NOTICE = 25
logging._levelNames[NOTICE] = 'NOTICE'
SysLogHandler.priority_map['NOTICE'] = 'notice'

# Used when reading config values
TRUE_VALUES = set(('true', '1', 'yes', 'on', 't', 'y'))


class StatsdEvent(object):

    def __init__(self, conf, logger, name_prepend=''):
        self.logger = logger
        self.statsd_host = conf.get('statsd_host', '127.0.0.1')
        self.statsd_port = int(conf.get('statsd_port', '8125'))
        self.statsd_addr = (self.statsd_host, self.statsd_port)
        self.statsd_sample_rate = float(conf.get('statsd_sample_rate', '.5'))
        self.combined_events = conf.get('combined_events',
                                        'no').lower() in TRUE_VALUES
        self.combine_key = conf.get('combine_key', '\n')
        if self.combine_key == "\\n":
            self.combine_key = '\n'
        self.metric_name_prepend = conf.get(
            'metric_name_prepend', name_prepend)
        self.actual_rate = 0.0
        self.count = 0
        self.monitored = 0
        self.enabled = conf.get('statsd_enable', 'n').lower() in TRUE_VALUES

    def _send_sampled_event(self):
        """"
        Check to see if statsd is even enabled. If it is track the sample rate
        and checks to see if this is a request that should be sent to statsd. If
        statsd support is disabled just return False and perform no ops.

        :returns: True if the event should be sent to statsd
        """
        if not self.enabled:
            return False
        send_sample = False
        self.count += 1
        if self.actual_rate < self.statsd_sample_rate:
            self.monitored += 1
            send_sample = True
        self.actual_rate = float(self.monitored) / float(self.count)
        if self.count >= maxint or self.monitored >= maxint:
            self.count = 0
            self.monitored = 0
        return send_sample

    def _send_events(self, payloads, combined_events=False):
        """Fire the actual udp events to statsd"""
        try:
            udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            if not combined_events:
                for payload in payloads:
                    print payload
                    udp_socket.sendto(payload, self.statsd_addr)
            else:
                # send multiple events per packet
                payload = self.combine_key.join(payloads)
                udp_socket.sendto(payload, self.statsd_addr)
        except Exception:
            self.logger.exception("Error sending statsd event")

    def batch_gauge(self, metric_dict, prefix='stalker.'):
        """Given a dict of metrics send all to statsd.
           Uses alternate key prefix! Doesn't use a sample rate."""
        if not self.enabled:
            return
        payload = []
        for k in metric_dict:
            payload.append('%s%s:%d|g' % (prefix, k, metric_dict[k]))
        self._send_events(payload)

    def counter(self, metric_name, value=1):
        """Send a counter event"""
        if self._send_sampled_event():
            counter = "%s%s:%d|c|@%s" % (self.metric_name_prepend, metric_name,
                                         value, self.statsd_sample_rate)
            self._send_events([counter])

    def timer(self, metric_name, duration):
        """Send a timer event"""
        if self._send_sampled_event():
            timer = "%s%s:%d|ms|@%s" % (self.metric_name_prepend, metric_name,
                                        duration, self.statsd_sample_rate)
            self._send_events(timer)


def get_basic_auth(user="", key=""):
    """Get basic auth creds

    :returns: the basic auth string
    """
    s = user + ":" + key
    return s.encode("base64").rstrip()


def get_logger(name, log_path='/var/log/stalker.log', level=logging.DEBUG,
               count=7, fmt=None):
    logger = logging.getLogger(name)
    handler = TimedRotatingFileHandler(log_path, when='midnight',
                                       backupCount=count)
    formatter = logging.Formatter('%(asctime)s - %(name)s: %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


def get_syslogger(conf, name=None, log_to_console=False, log_route=None,
                  fmt=None):
    """
    Stolen from: Openstack Swift
    Get the current system logger using config settings.

    **Log config and defaults**::

        log_facility = LOG_LOCAL0
        log_level = INFO
        log_name = swift
        log_udp_host = (disabled)
        log_udp_port = logging.handlers.SYSLOG_UDP_PORT
        log_address = /dev/log

    :param conf: Configuration dict to read settings from
    :param name: Name of the logger
    :param log_to_console: Add handler which writes to console on stderr
    :param log_route: Route for the logging, not emitted to the log, just used
                      to separate logging configurations
    :param fmt: Override log format
    """
    if not conf:
        conf = {}
    if name is None:
        name = conf.get('log_name', 'stalker')
    if not log_route:
        log_route = name
    logger = logging.getLogger(log_route)
    logger.propagate = False
    # all new handlers will get the same formatter
    if not fmt:
        formatter = logging.Formatter('%(name)s: %(message)s')
    else:
        formatter = logging.Formatter(fmt)

    # get_logger will only ever add one SysLog Handler to a logger
    if not hasattr(get_logger, 'handler4logger'):
        get_logger.handler4logger = {}
    if logger in get_logger.handler4logger:
        logger.removeHandler(get_logger.handler4logger[logger])

    # facility for this logger will be set by last call wins
    facility = getattr(SysLogHandler, conf.get('log_facility', 'LOG_LOCAL0'),
                       SysLogHandler.LOG_LOCAL0)
    udp_host = conf.get('log_udp_host')
    if udp_host:
        udp_port = int(conf.get('log_udp_port',
                                logging.handlers.SYSLOG_UDP_PORT))
        handler = SysLogHandler(address=(udp_host, udp_port),
                                facility=facility)
    else:
        log_address = conf.get('log_address', '/dev/log')
        try:
            handler = SysLogHandler(address=log_address, facility=facility)
        except socket.error, e:
            # Either /dev/log isn't a UNIX socket or it does not exist at all
            if e.errno not in [errno.ENOTSOCK, errno.ENOENT]:
                raise e
            handler = SysLogHandler(facility=facility)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    get_logger.handler4logger[logger] = handler

    # setup console logging
    if log_to_console or hasattr(get_logger, 'console_handler4logger'):
        # remove pre-existing console handler for this logger
        if not hasattr(get_logger, 'console_handler4logger'):
            get_logger.console_handler4logger = {}
        if logger in get_logger.console_handler4logger:
            logger.removeHandler(get_logger.console_handler4logger[logger])

        console_handler = logging.StreamHandler(sys.__stderr__)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        get_logger.console_handler4logger[logger] = console_handler

    # set the level for the logger
    logger.setLevel(
        getattr(logging, conf.get('log_level', 'INFO').upper(), logging.INFO))

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

 
#class RedisLockTimeout(BaseException):
#	pass
# 
#class RedisLock(object):
# 
#	"""
#	Implements a distributed lock using Redis.
#	"""
# 
#	def __init__(self, redis, lock_type, key, expires=30, timeout=20):
#		self.key = key
#		self.lock_type = lock_type
#		self.redis = redis
#		self.timeout = timeout
#		self.expires = expires
# 
#	def lock_key(self):
#		return "%s:locks:%s" % (self.lock_type,self.key)
# 
#	def __enter__(self):
#		timeout = self.timeout
#		while timeout >= 0:
#			expires = time.time() + self.expires + 1
#			pipe = self.redis.pipeline()
#			lock_key = self.lock_key()
#			pipe.watch(lock_key)
#			try:
#				lock_value = float(self.redis.get(lock_key))
#			except (ValueError,TypeError):
#				lock_value = None
#			if not lock_value or lock_value < time.time():
#				try:
#					pipe.multi()
#					pipe.set(lock_key,expires)
#					pipe.expire(lock_key,self.expires+1)
#					pipe.execute()
#					return expires
#				except WatchError:
#					print "Someone tinkered with the lock!"
#					pass
#			timeout -= 0.01
#			eventlet.sleep(0.01)
#		raise RedisLockTimeout("Timeout while waiting for redis lock")
# 
#	def __exit__(self, exc_type, exc_value, traceback):
#		self.redis.delete(self.lock_key())
