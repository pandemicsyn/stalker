import os
import errno
import signal
from time import time

import eventlet
from eventlet.green import urllib2

from bson import ObjectId
from bson.json_util import loads

from stalker.stalker_utils import Daemon, get_logger, get_syslogger, \
    TRUE_VALUES, StatsdEvent
eventlet.monkey_patch()
import redis
from pymongo import MongoClient


class StalkerRunner(object):

    def __init__(self, conf):
        self.conf = conf
        self.name = 'stalker-runner-%d' % os.getpid()
        log_type = conf.get('log_type', 'syslog')
        log_file = conf.get('log_file', '/var/log/stalker/stalker-runner.log')
        if log_type == 'syslog':
            self.logger = get_syslogger(conf, self.name)
        else:
            self.logger = get_logger(self.name, log_path=log_file)
        self.pool = eventlet.GreenPool()
        self.check_key = conf.get('check_key', 'canhazstatus')
        redis_host = conf.get('redis_host', '127.0.0.1')
        redis_port = int(conf.get('redis_port', '6379'))
        redis_pass = conf.get('redis_password', '')
        redis_usock = conf.get('redis_socket', None)
        self.wq = conf.get('worker_id', 'worker1')
        self.rc = redis.Redis(redis_host, redis_port, password=redis_pass,
                              unix_socket_path=redis_usock)
        mongo_host = conf.get('mongo_host', '127.0.0.1')
        mongo_port = int(conf.get('mongo_port', '27017'))
        db_name = conf.get('db_name', 'stalkerweb')
        self.c = MongoClient(host=mongo_host, port=mongo_port)
        self.debug = False
        self.db = self.c[db_name]
        self.checks = self.db['checks']
        self.state_log = self.db['state_log']
        self.notifications = self.db['notifications']
        self.host_window = int(conf.get('host_flood_window', '60'))
        self.host_threshold = int(conf.get('host_flood_threshold', '5'))
        self.flood_window = int(conf.get('dc_flood_window', '120'))
        self.flood_threshold = int(conf.get('dc_flood_threshold', '100'))
        self.flap_window = int(conf.get('flap_window', '1200'))
        self.flap_threshold = int(conf.get('flap_threshold', '5'))
        self.alert_threshold = int(conf.get('alert_threshold', '3'))
        self.urlopen_timeout = int(conf.get('urlopen_timeout', '15'))
        self.notify_plugins = {}
        self._load_notification_plugins(conf)
        self.statsd = StatsdEvent(conf, self.logger, 'stalker_runner.')

    def _load_notification_plugins(self, conf):
        """Load any enabled notification plugins"""
        if conf.get('mailgun_enable', 'n').lower() in TRUE_VALUES:
            from stalker_notifications import Mailgun
            mailgun = Mailgun(
                conf=conf, logger=self.logger, redis_client=self.rc)
            self.notify_plugins['mailgun'] = mailgun
        if conf.get('http_enable', 'n').lower() in TRUE_VALUES:
            from stalker_notifications import GenericHTTP
            generichttp = GenericHTTP(conf=conf, logger=self.logger,
                                      redis_client=self.rc)
            self.notify_plugins['generichttp'] = generichttp
        if conf.get('pagerduty_enable', 'n').lower() in TRUE_VALUES:
            from stalker_notifications import PagerDuty
            pagerduty = PagerDuty(conf=conf, logger=self.logger,
                                  redis_client=self.rc)
            self.notify_plugins['pagerduty'] = pagerduty
        if conf.get('smtplib_enable', 'n').lower() in TRUE_VALUES:
            from stalker_notifications import EmailNotify
            email_notify = EmailNotify(conf=conf, logger=self.logger,
                                       redis_client=self.rc)
            self.notify_plugins['email_notify'] = email_notify

    def _get_checks(self, max_count=100, max_time=1, timeout=1):
        """Gather some checks off the Redis queue and batch them up"""
        checks = []
        expire_time = time() + max_time
        while len(checks) != max_count:
            if len(checks) > 0 and time() > expire_time:
                # we've exceeded our max_time return what we've got at
                # least
                return checks
            c = self.rc.blpop(self.wq, timeout=timeout)
            eventlet.sleep()
            if c:
                checks.append(c)
                self.logger.debug("grabbed check")
            else:
                if len(checks) > 0:
                    return checks
                else:
                    # still have no checks, keep waiting
                    pass
        return checks

    def _exec_check(self, url):
        """Actually execute a check on the remote host"""
        req = urllib2.Request(url, headers={'X-CHECK-KEY': self.check_key})
        response = urllib2.urlopen(req, timeout=self.urlopen_timeout)
        content = response.read()
        if not content:
            raise Exception("No content")
        return loads(content)

    def _flap_incr(self, flapid):
        """incr flap counter for a specific check"""
        pipe = self.rc.pipeline()
        pipe.multi()
        pipe.incr(flapid)
        pipe.expire(flapid, self.flap_window)
        pipe.execute()

    def _log_state_change(self, check):
        """Log that a state change occurred in the state_log table"""
        try:
            self.state_log.insert({'hostname': check['hostname'],
                                   'check': check['check'],
                                   'cid': check['_id'],
                                   'status': check['status'],
                                   'last': check['last'],
                                   'out': check['out'],
                                   'owner': check.get('owner', '')})
        except Exception:
            self.logger.exception('Error writing to state_log')

    def host_ncount(self, hostname):
        """Get a count of how many outstanding notifications a host has"""
        return self.notifications.find({'hostname': hostname}).count()

    def host_flood(self, hostname):
        """Check if a host is flooding"""
        count = self.notifications.find({"ts": {"$gt": time() - self.host_window},
                                         "hostname": hostname}).count()
        if count > self.host_threshold:
            self.logger.info('Host flood detected. Suppressing alerts for %s' % hostname)
            return True
        else:
            return False

    def global_flood(self):
        """Check if we're experiencing a global alert flood"""
        count = self.notifications.find({"ts": {"$gt": time() - self.flood_window}}).count()
        if count > self.flood_threshold:
            self.logger.info('Global alert flood detected. Suppressing alerts')
            return True
        else:
            return False

    def flapping(self, flapid):
        """Check if a check is flapping"""
        flap_count = int(self.rc.get(flapid) or 0)
        self.logger.debug('%s %d' % (flapid, flap_count))
        if flap_count >= self.flap_threshold:
            return True
        else:
            return False

    def _emit_fail(self, check):
        """Emit a failure event via the notification plugins"""
        self.logger.info('alert %s' % check)
        for plugin in self.notify_plugins.itervalues():
            try:
                plugin.fail(check)
            except Exception:
                self.logger.exception('Error emitting failure')

    def _emit_clear(self, check):
        """Emit a clear event via the notification plugins"""
        self.logger.info('cleared %s' % check)
        for plugin in self.notify_plugins.itervalues():
            try:
                plugin.clear(check)
            except Exception:
                self.logger.exception('Error emitting clear')

    def check_failed(self, check):
        """Perform failure notifications if required"""
        if not self.notifications.find_one({'hostname': check['hostname'],
                                            'check': check['check']}):
            n = {'cid': check['_id'], 'hostname': check['hostname'],
                 'check': check['check'], 'ts': time(), 'cleared': False}
            try:
                q = self.notifications.insert(n)
            except Exception:
                self.logger.exception('Error updating notifications table!')
                return
            if not self.host_flood(check['hostname']) and not self.global_flood():
                self._emit_fail(check)
        else:
            self.logger.debug('Notification entry already exists!')

    def check_cleared(self, check):
        """Perform clear notifications if required"""
        if self.notifications.find_one({'hostname': check['hostname'],
                                        'check': check['check']}):
            try:
                q = self.notifications.remove({'hostname': check['hostname'], 'check': check['check']})
            except Exception:
                self.logger.exception('Error removing notifications entry.')
            self._emit_clear(check)
        else:
            self.logger.debug('No notification entry to clear')

    def emit_host_flood_alert(self, hostname):
        """Emit a host level flood alert via the notification plugins"""
        check = {'hostname': hostname, 'check': 'host_alert_flood',
                 'out': 'Host level alert flood detected!'}
        for plugin in self.notify_plugins.itervalues():
            try:
                plugin.fail(check)
            except Exception:
                self.logger.exception('Error emitting failure')

    def emit_flood_alert(self):
        """Emit a flood notification event via the notification plugins"""
        check = {'hostname': 'alertflood', 'check': 'dc_alert_flood',
                 'out': 'DC wide alert flood detected!'}
        for plugin in self.notify_plugins.itervalues():
            try:
                plugin.fail(check)
            except Exception:
                self.logger.exception('Error emitting failure')

    def state_has_changed(self, check, previous_status):
        """Determin if a state has changed, and update state log accordingly"""
        if check['status'] != previous_status:
            self.logger.debug('%s:%s state changed.' % (check['hostname'],
                                                        check['check']))
            self._log_state_change(check)
            state_changed = True
            self.statsd.counter('state_change')
        else:
            self.logger.debug('%s:%s state unchanged.' % (check['hostname'],
                                                          check['check']))
            state_changed = False
        return state_changed

    def state_change(self, check, previous_status):
        """Handle check result state changes"""
        state_changed = self.state_has_changed(check, previous_status)
        if check['status'] is True and state_changed is True:
            self.check_cleared(check)
        elif check['status'] is False:
            # we don't check if state_changed to allow for alert escalations
            # at a later date. In the mean time this means check_failed gets
            # called everytime a check is run and fails.
            self.logger.info('%s:%s failure # %d' % (check['hostname'],
                                                     check['check'],
                                                     check['fail_count']))
            if check['flapping']:
                self.logger.info('%s:%s is flapping - skipping fail/clear event' %
                                (check['hostname'], check['check']))
                #emit_flap notification
            elif check['fail_count'] >= self.alert_threshold:
                self.check_failed(check)

    def run_check(self, payload):
        """Run a check and process its result"""
        check = loads(payload[1])
        check_name = check['check']
        flapid = "flap:%s:%s" % (check['hostname'], check['check'])
        previous_status = check['status']
        try:
            result = self._exec_check('https://%s:5050/%s' % (check['ip'],
                                                              check_name))
        except Exception as err:
            result = {check_name: {'status': 2, 'out': '', 'err': str(err)}}
            self.statsd.counter('checks.error')
        if result[check_name]['status'] == 0:
            if previous_status is False:
                self._flap_incr(flapid)
            query = {'_id': ObjectId(check['_id'])}
            update = {"$set": {'pending': False, 'status': True,
                               'flapping': self.flapping(flapid),
                               'next': time() + check['interval'],
                               'last': time(),
                               'out': result[check_name]['out'] +
                               result[check_name]['err'],
                               'owner': '',
                               'fail_count': 0}}
            self.statsd.counter('checks.passed')
        else:  # check is failing
            if previous_status is True:
                self._flap_incr(flapid)
            query = {'_id': ObjectId(check['_id'])}
            if 'follow_up' not in check:  # continue to work with old schema
                check['follow_up'] = check['interval']
            update = {"$set": {'pending': False, 'status': False,
                               'flapping': self.flapping(flapid),
                               'next': time() + check['follow_up'],
                               'last': time(),
                               'out': result[check_name]['out'] +
                               result[check_name]['err']},
                      "$inc": {'fail_count': 1}}
            self.statsd.counter('checks.failed')
        try:
            response = self.checks.find_and_modify(query=query, update=update,
                                                   new=True)
        except Exception:
            response = None
            self.logger.exception('Error on check find_and_modify:')
        if response:
            self.state_change(response, previous_status)
            return True
        else:
            return False

    def start(self):
        while 1:
            self.logger.debug("Checking queue for work")
            checks = self._get_checks()
            if checks:
                count = len(checks)
                self.logger.debug("Got %d checks" % count)
                self.statsd.counter('queue.get', count)
                try:
                    check_result = [x for x in self.pool.imap(self.run_check,
                                                              checks)]
                    self.logger.debug(check_result)
                except Exception:
                    self.logger.exception('Error running checks')
            else:
                self.logger.debug('No checks, sleeping')
            eventlet.sleep()


class SRDaemon(Daemon):

    def run(self, conf):

        name = 'stalker-agent'
        log_type = conf.get('log_type', 'syslog')
        log_file = conf.get('log_path', '/var/log/stalker/stalker-runner.log')
        if log_type == 'syslog':
            logger = get_syslogger(conf, name)
        else:
            logger = get_logger(name, log_path=log_file)

        def spawn_worker():
            sr = StalkerRunner(conf)
            while 1:
                try:
                    sr.start()
                except Exception as err:
                    logger.info(err)

        worker_count = int(conf.get('workers', '1'))

        def kill_children(*args):
            """Kills the entire process group."""
            logger.error('SIGTERM received')
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            running[0] = False
            os.killpg(0, signal.SIGTERM)

        def hup(*args):
            """Shuts down the server, but allow running requests to complete"""
            logger.error('SIGHUP received')
            signal.signal(signal.SIGHUP, signal.SIG_IGN)
            running[0] = False

        running = [True]
        signal.signal(signal.SIGTERM, kill_children)
        signal.signal(signal.SIGHUP, hup)
        children = []
        while running[0]:
            while len(children) < worker_count:
                pid = os.fork()
                if pid == 0:
                    signal.signal(signal.SIGHUP, signal.SIG_DFL)
                    signal.signal(signal.SIGTERM, signal.SIG_DFL)
                    spawn_worker()
                    logger.info('Child %d exiting normally' % os.getpid())
                    return
                else:
                    logger.info('Started child %s' % pid)
                    children.append(pid)
            try:
                pid, status = os.wait()
                if os.WIFEXITED(status) or os.WIFSIGNALED(status):
                    logger.error('Removing dead child %s' % pid)
                    if pid in children:
                        children.remove(pid)
            except OSError, err:
                if err.errno not in (errno.EINTR, errno.ECHILD):
                    raise
            except KeyboardInterrupt:
                break
