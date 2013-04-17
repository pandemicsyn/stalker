import urllib2
from time import time

import eventlet
from bson import ObjectId
from bson.json_util import loads
from stalker_utils import Daemon, get_logger, TRUE_VALUES
eventlet.monkey_patch()
import redis
from pymongo import MongoClient


class StalkerRunner(object):

    def __init__(self, conf):
        self.conf = conf
        log_file = conf.get('log_path', '/var/log/stalker/stalker-runner.log')
        self.logger = get_logger('stalker_runner', log_path=log_file)
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
        self.flap_window = int(conf.get('flap_window', '1200'))
        self.flap_threshold = int(conf.get('flap_threshold', '5'))
        self.alert_threshold = int(conf.get('alert_threshold', '3'))
        self.notifications = {}
        self._load_notification_plugins(conf)


    def _load_notification_plugins(self, conf):
        if conf.get('mailgun_enable', 'n').lower() in TRUE_VALUES:
            from stalker_notifications import Mailgun
            mailgun = Mailgun(conf=conf, logger=self.logger, redis_client=self.rc)
            self.notifications['mailgun'] = mailgun
        if conf.get('pagerduty_enable', 'n').lower() in TRUE_VALUES:
            from stalker_notifications import PagerDuty
            pagerduty = PagerDuty(conf=conf, logger=self.logger,
                                  redis_client=self.rc)
            self.notifications['pagerduty'] = pagerduty
        if conf.get('smtplib_enable', 'n').lower() in TRUE_VALUES:
            from stalker_notifications import EmailNotify
            email_notify = EmailNotify(conf=conf, logger=self.logger,
                                       redis_client=self.rc)
            self.notifications['email_notify'] = email_notify

    def _get_checks(self, max_count=100, max_time=2, timeout=2):
            """Gather some checks off the Redis queue and batch them up"""
            checks = []
            expire_time = time() + max_time
            while len(checks) != max_count:
                if len(checks) > 0 and time() > expire_time:
                    # we've exceeded our max_time return what we've got at
                    # least
                    return checks
                stat = self.rc.blpop(self.wq, timeout=timeout)
                eventlet.sleep()
                if stat:
                    checks.append(stat)
                    self.logger.debug("grabbed check")
                else:
                    if len(checks) > 0:
                        return checks
                    else:
                        # still have no checks, keep waiting
                        pass
            return checks

    def _fetch_url(self, url):
        req = urllib2.Request(url, headers={'X-CHECK-KEY': self.check_key})
        response = urllib2.urlopen(req)
        content = response.read()
        if not content:
            raise Exception("No content")
        return loads(content)

    def _flap_incr(self, flapid):
        self.rc.incr(flapid)
        self.rc.expire(flapid, self.flap_window)

    def flapping(self, flapid):
        flap_count = int(self.rc.get(flapid) or 0)
        self.logger.debug('%s %d' % (flapid, flap_count))
        if flap_count >= self.flap_threshold:
            return True
        else:
            return False

    def emit_fail(self, check):
        self.logger.info('alert %s' % check)
        for plugin in self.notifications.itervalues():
            try:
                plugin.fail(check)
            except Exception:
                self.logger.exception('Error emitting failure: ')

    def emit_clear(self, check):
        self.logger.info('cleared %s' % check)
        for plugin in self.notifications.itervalues():
            try:
                plugin.clear(check)
            except Exception:
                self.logger.exception('Error emitting failure: ')

    def state_change(self, check, previous_status):
        if check['status'] != previous_status:
            self.logger.info('%s:%s state changed.' % (check['hostname'],
                                                       check['check']))
            state_changed = True
        else:
            self.logger.debug('%s:%s state unchanged.' % (check['hostname'],
                                                          check['check']))
            state_changed = False

        if check['status'] is True and not check['flapping']:
            if state_changed:
                self.emit_clear(check)
        elif check['status'] is True and check['flapping']:
            self.logger.info('%s:%s is flapping - skipping notification.' %
                             (check['hostname'], check['check']))
        elif check['status'] is False and not check['flapping']:
            if check['fail_count'] >= self.alert_threshold:
                self.logger.info('%s:%s failure # %d' % (check['hostname'],
                                                         check['check'],
                                                         check['fail_count']))
                self.emit_fail(check)
            else:
                self.logger.info('%s:%s failure # %d' % (check['hostname'],
                                                         check['check'],
                                                         check['fail_count']))
        elif check['status'] is False and check['flapping']:
            self.logger.info('%s:%s is flapping - skipping notification.' %
                             (check['hostname'], check['check']))
        else:
            self.logger.info("Oops, odd state. Shouldn't have got here.")
        return state_changed

    def run_check(self, payload):
        check = loads(payload[1])
        check_name = check['check']
        flapid = "flap:%s:%s" % (check['hostname'], check['check'])
        ip = check['ip']
        previous_status = check['status']
        result = None
        try:
            result = self._fetch_url('http://%s:5050/%s' % (ip, check_name))
        except Exception as err:
            result = {check_name: {'status': 2, 'out': '', 'err': str(err)}}

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
                               'fail_count': 0}}
        else:
            if previous_status is True:
                self._flap_incr(flapid)
            query = {'_id': ObjectId(check['_id'])}
            update = {"$set": {'pending': False, 'status': False,
                               'flapping': self.flapping(flapid),
                               'next': time() + check['interval'],
                               'last': time(),
                               'out': result[check_name]['out'] +
                               result[check_name]['err']},
                      "$inc": {'fail_count': 1}}
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
                self.logger.info("Got %d checks" % len(checks))
                check_result = [x for x in self.pool.imap(self.run_check,
                                                          checks)]
                self.logger.debug(check_result)
            else:
                self.logger.debug('No checks, sleeping')
            eventlet.sleep()


class SRDaemon(Daemon):

    def run(self, conf):
        sr = StalkerRunner(conf)
        while 1:
            sr.start()
