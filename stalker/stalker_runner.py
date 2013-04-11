import urllib2
from time import time

import eventlet
from bson.json_util import loads
from stalker_utils import Daemon, get_logger
eventlet.monkey_patch()
import redis
from pymongo import MongoClient


class StalkerRunner(object):

    def __init__(self, conf):
        self.conf = conf
        log_file = conf.get('log_path', '/var/log/stalker-runner.log')
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
        self.flap_threshold = int(conf.get('flap_threshold', '3'))
        self.alert_threshold = int(conf.get('alert_threshold', '2'))
        self.alert_expire = int(conf.get('alert_expire', '1800'))

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

    def emit_alert(self, check):
        self.logger.info('alert %s' % check)

    def status_update(self, host, check, status, previous_status):
        flapid = "flap:%s:%s" % (host, check)
        failid = "failed:%s:%s" % (host, check['check'])
        notifyid = "notified:%s:%s" % (host, check['check'])
        if status != previous_status:
            #state changed incr flap counter
            self.rc.incr(flapid)
            self.rc.expire(flapid, self.flap_window)
        if status is False:
            self.rc.incr(failid)
            if self.flapping(flapid):
                #we failed again but it looks like we're flapping
                self.logger.info('%s is flapping - skipping notification.' % flapid)
                self.logger.info('%s:%s failure # %d'% (host, check['check'], int(self.rc.get(failid) or 0)))
            else:
                fail_count = int(self.rc.get(failid) or 0)
                notify_count = int(self.rc.get(notifyid) or 0)
                if fail_count >= self.alert_threshold:
                    if notify_count > 0:
                        self.logger.info('%s:%s failure # %d - previously notified' % (host, check['check'], fail_count))
                        #We've already emited an alert
                    else:
                        #emit an alert
                        self.logger.info('%s:%s failure # %d'% (host, check['check'], fail_count))
                        self.emit_alert(check)
                        self.rc.setex(notifyid, 1, self.alert_expire)
                else:
                    #we failed but haven't reached the alert threshold yet
                    self.logger.info('%s:%s failure # %d' % (host, check['check'], fail_count))
        else:
            if previous_status is False:
                self.logger.info('%s:%s alert cleared' % (host, check['check']))
                #check is responding again, clear alert
                self.rc.delete(notifyid)

    def flapping(self, flapid):
        flap_count = int(self.rc.get(flapid) or 0)
        if flap_count >= self.flap_threshold:
            return True
        else:
            return False

    def run_check(self, payload):
        check = loads(payload[1])
        host = check['hostname']
        check_name = check['check']
        ip = check['ip']
        flapid = 'flap:%s:%s' % (host, check_name)
        current_status = check['status']
        result = None
        try:
            result = self._fetch_url(
                'http://%s:5050/%s' % (ip, check_name))
        except Exception as err:
            result = {check_name: {'status': 2, 'out': '', 'err': str(err)}}
        now = time()
        if result[check_name]['status'] == 0:
            self.rc.set("failed:%s:%s" % (host, check_name), "0")
            self.status_update(host, check, True, current_status)
            u = self.checks.update({'_id': check['_id']},
                                   {"$set": {'pending': False, 'status': True,
                                             'flapping': self.flapping(flapid),
                                             'last': now,
                                             'next': now + check['interval'],
                                             'out': result[check_name]['out']
                                             }})
        else:
            self.status_update(host, check, False, current_status)
            u = self.checks.update({'_id': check['_id']},
                                   {"$set": {'pending': False, 'status': False,
                                             'flapping': self.flapping(flapid),
                                             'last': now,
                                             'next': now + check['interval'],
                                             'out': result[check_name]['out'] + result[check_name]['err']
                                             }})
        return u

    def start(self):
        while 1:
            self.logger.debug("Checking queue for work")
            checks = self._get_checks()
            if checks:
                self.logger.info("Got %d checks" % len(checks))
                check_result = [x for x in self.pool.imap(
                    self.run_check, checks)]
                for check in check_result:
                    if check['updatedExisting'] and check['err'] is None:
                        self.logger.debug(check)
                    else:
                        self.logger.error(check)
            else:
                self.logger.debug('No checks, sleeping')
            eventlet.sleep()


class SRDaemon(Daemon):

    def run(self, conf):
        sr = StalkerRunner(conf)
        while 1:
            sr.start()
