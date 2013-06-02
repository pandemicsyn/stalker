import redis
from random import choice
from os.path import exists
from time import time, sleep
from pymongo import MongoClient
from bson.json_util import dumps
from stalker.stalker_utils import Daemon, StatsdEvent, get_logger


class StalkerManager(object):

    def __init__(self, conf):
        self.conf = conf
        log_file = conf.get('log_path', '/var/log/stalker/stalker-manager.log')
        self.logger = get_logger('stalker_manager', log_path=log_file)
        redis_host = conf.get('redis_host', '127.0.0.1')
        redis_port = int(conf.get('redis_port', '6379'))
        redis_pass = conf.get('redis_password', '')
        redis_usock = conf.get('redis_socket', None)
        self.wq = conf.get('qname', 'worker1')
        self.rc = redis.Redis(redis_host, redis_port, password=redis_pass,
                              unix_socket_path=redis_usock)
        mongo_host = conf.get('mongo_host', '127.0.0.1')
        mongo_port = int(conf.get('mongo_port', '27017'))
        db_name = conf.get('db_name', 'stalkerweb')
        self.c = MongoClient(host=mongo_host, port=mongo_port)
        self.db = self.c[db_name]
        self.checks = self.db['checks']
        self.scan_interval = int(conf.get('scan_interval', '5'))
        self.pause_file = conf.get('pause_file', '/tmp/.sm-pause')
        self.shuffle_on_start = True
        self.statsd = StatsdEvent(conf, self.logger, 'stalker_manager.')
        self.metrics = {'checks': 0, 'pending': 0, 'suspended': 0,
                        'failing': 0, 'flapping': 0, 'qsize': 0}

    def _collect_metrics(self):
        self.metrics['checks'] = self.checks.count()
        self.metrics['pending'] = self.checks.find({'pending': True}).count()
        self.metrics['suspended'] = self.checks.find({'suspended':
                                                     True}).count()
        self.metrics['failing'] = self.checks.find({'status': False}).count()
        self.metrics['flapping'] = self.checks.find({'status': False}).count()
        self.metrics['qsize'] = self.queue_len()
        self.logger.info("stats: %s" % self.metrics)
        self.rc.mset(self.metrics)
        self.statsd.batch_gauge(self.metrics, prefix='stalker.')

    def startup_shuffle(self):
        # reshuffle all checks that need to be done right now and schedule
        # them for a future time. i.e. if the stalker-manager was offline
        # for an extended period of time.
        if not self.shuffle_on_start:
            return
        else:
            count = 0
            for i in self.checks.find({'next': {"$lt": time()}}):
                r = self.checks.update({'_id': i['_id']},
                                       {"$set": {"next": time() + choice(xrange(600))}})
                count += 1
            self.logger.info('Reshuffled %d checks on startup.' % count)

    def pause_if_asked(self):
        """Check if pause file exists and sleep until its removed if it does"""
        if exists(self.pause_file):
            self.logger.info('Pausing')
            while exists(self.pause_file):
                sleep(1)
            self.logger.info('Pause removed')

    def queue_len(self, q='worker1'):
        """Return # of items in queue"""
        return self.rc.llen(q)

    def queue_check(self, i):
        """Queue up a check for the stalker_runners"""
        # if we had multiple stalker_runners we could roundrobin q's
        self.rc.rpush('worker1', dumps(i))

    def sanitize(self, flush_queued=True):
        """scan the checks db for checks marked pending but not actually
        in progress. i.e. redis died, or services where kill -9'd."""
        pending = [x['_id'] for x in self.checks.find(
            {'pending': True}, fields={'_id': True})]
        self.logger.warning('Found %d pending items' % len(pending))
        if flush_queued:
            self.rc.delete('worker1')
            q = self.checks.update(
                {'pending': True}, {'$set': {'pending': False}}, multi=True)
            if q['err']:
                raise Exception('Error clearing pendings')
        else:
            q = self.checks.update(
                {'pending': True}, {'$set': {'pending': False}}, multi=True)
            if q['err']:
                raise Exception('Error clearing pendings')

    def scan_checks(self):
        """scan the checks db for checks that need to run
        mark them as pending and then drop'em on the q for the runner."""
        self.pause_if_asked()
        qcount = 0
        for check in self.checks.find({'next': {"$lt": time()},
                                       'pending': False,
                                       'suspended': False}):
            try:
                u = self.checks.update({'_id': check['_id']},
                                       {"$set": {'pending': True}})
                if u['updatedExisting']:
                    self.queue_check(check)
                    qcount += 1
            except Exception as err:
                try:
                    u = self.checks.update({'_id': check['_id']},
                                           {"$set": {'pending': True}})
                except Exception as err2:
                    self.logger.error(err2)
                self.logger.error(err)
        if qcount > 0:
            self.logger.info('Queued %d checks' % qcount)
            self.statsd.counter('queue.put', qcount)
        self._collect_metrics()

    def start(self):
        self.logger.info('starting up')
        self.sanitize()
        self.startup_shuffle()
        while 1:
            try:
                self.scan_checks()
                sleep(self.scan_interval)
            except Exception as err:
                print err


class SMDaemon(Daemon):

    def run(self, conf):
        sm = StalkerManager(conf)
        while 1:
            sm.start()
