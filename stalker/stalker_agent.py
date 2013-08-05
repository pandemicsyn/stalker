import os
import json
from eventlet import wsgi
from eventlet.green import subprocess, urllib2
from socket import gethostname
import eventlet
from stalker.stalker_utils import Daemon, FileLikeLogger, readconf, get_logger


class StalkerAgent(object):

    def __init__(self, fullconf):
        conf = fullconf['main']
        self.fullconf = fullconf
        log_file = conf.get('log_path', '/var/log/stalker/stalker-agent.log')
        self.logger = get_logger('stalker_agent', log_path=log_file)
        self.request_logger = FileLikeLogger(self.logger)
        self.listen_addr = conf.get('listen_addr', '')
        self.listen_port = int(conf.get('listen_port', '5050'))
        self.ssl_crt_path = conf.get('ssl_cert', '/etc/stalker/ssl.crt')
        self.ssl_key_path = conf.get('ssl_key', '/etc/stalker/ssl.key')
        self.master_url = conf.get('master_url', 'http://localhost:5000')
        if self.master_url.startswith('https://'):
            self.master_scheme = 'https'
        else:
            self.master_scheme = 'http'
        self.register_key = conf.get('register_key', 'itsamario')
        self.check_key = conf.get('check_key', 'canhazstatus')
        self.script_dir = conf.get('script_dir', '/etc/stalker/scripts')
        self.default_interval = int(conf.get('default_interval', '300'))
        self.scripts = {}
        self.hostname = conf.get('hostname', gethostname())
        self.roles = [x.strip() for x in conf.get('roles',
                                                  'server').split(',')]
        if not os.path.exists(self.script_dir):
            raise Exception("No script dir: %s" % self.script_dir)
        self._build_check_list()
        self.logger.info('Found checks: %s' % self.scripts)

    def _build_check_list(self):
        """Build our list of checks and their config"""
        self._get_scripts_from_conf()
        for i in os.listdir(self.script_dir):
            if self._script_ok(i):
                self.scripts[i] = self._script_config(i)

    def _script_ok(self, script_name):
        """Verify this is a check script and we have exec perms"""
        tgt = os.path.join(self.script_dir, script_name)
        if os.path.splitext(tgt)[1] == '.cfg':
            return False  # this is a config file
        else:
            if '.' in script_name or '$' in script_name:
                self.logger.error("name contains . or $: %s" % script_name)
                return False
        if os.path.isfile(tgt):
            if os.access(tgt, os.X_OK):
                return True
            else:
                return False
        else:
            return False

    def _get_scripts_from_conf(self):
        for check in self.fullconf:
            if not check.startswith('check_'):
                continue
            if self.fullconf[check].get('enabled', 'true').lower() != 'true':
                self.logger.info('%s disabled. skipping.' % check)
                continue
            cmd = self.fullconf[check].get('cmd')
            args = self.fullconf[check].get('args') or ''
            interval = int(self.fullconf[check].get('interval',
                                                    self.default_interval))
            follow_up = int(self.fullconf[check].get('follow_up', interval))
            if not cmd:
                self.logger.warning('No cmd specified for %s skipping' % check)
            elif not os.path.isfile(cmd) or not os.access(cmd, os.X_OK):
                self.logger.warning('%s cmd not executable or not file' % cmd)
            else:
                self.logger.info('found %s check' % cmd)
                self.scripts[check] = {'cmd': cmd, 'args': args,
                                       'interval': interval,
                                       'follow_up': follow_up}

    def _script_config(self, script_name):
        """Check if theres a .cfg for a given script, if so load the config"""
        if os.path.exists(os.path.join(self.script_dir, script_name + '.cfg')):
            sconf = readconf(os.path.join(self.script_dir,
                                          script_name + '.cfg'))['default']
        else:
            sconf = {}
        return {'cmd': os.path.join(self.script_dir, script_name),
                'args': sconf.get('args', ''),
                'interval': int(sconf.get('interval', self.default_interval)),
                'follow_up': int(sconf.get('follow_up',
                                           sconf.get('interval',
                                                     self.default_interval)))}

    def notify_master(self):
        """Send master our config"""
        target = '%s/register' % (self.master_url)
        data = json.dumps({'hostname': self.hostname, 'checks': self.scripts,
                           'roles': self.roles})
        req = urllib2.Request(target, data,
                              {'Content-Type': 'application/json'})
        req.add_header("X-REGISTER-KEY", self.register_key)
        try:
            r = urllib2.urlopen(req)
            headers = r.info().dict
            text = r.read()
            r.close()
            self.logger.info('Notified master: %s %s %d' % (headers, text,
                                                            r.code))
            return True
        except Exception as err:
            self.logger.error('Error notifying master: %s' % err)
            return False

    def single(self, env, start_response):
        """Process a single a check call"""
        script = env['PATH_INFO'].strip('/')
        p = subprocess.Popen("%s %s" % (self.scripts[script]['cmd'],
                                        self.scripts[script]['args']),
                             shell=True, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        stouterr = p.communicate()
        status = {'%s' % script: {'status': p.returncode,
                                  'out': stouterr[0].strip(),
                                  'err': stouterr[1].strip()}}
        start_response('200 OK', [('Content-Type', 'application/json')])
        return ['%s\r\n' % json.dumps(status)]

    def handle_request(self, env, start_response):
        if env.get('HTTP_X_CHECK_KEY') != self.check_key:
            start_response('401 Unauthorized',
                           [('Content-Type', 'text/plain')])
            return ['Unauthorized\r\n']
        if env['PATH_INFO'].startswith('/check_'):
            if env['PATH_INFO'].strip('/') in self.scripts:
                try:
                    return self.single(env, start_response)
                except Exception as err:
                    start_response('500 Internal Server Error',
                                   [('Content-Type', 'text/plain')])
                    return ['Error running check: %s' % err]
            else:
                start_response('404 Not Found',
                               [('Content-Type', 'text/plain')])
                return ['No such check\r\n']
        else:
            start_response('404 Not Found', [('Content-Type', 'text/plain')])
            return ['Not Found\r\n']

    def start(self):
        try:
            wsgi.server(eventlet.wrap_ssl(eventlet.listen((self.listen_addr,
                                                           self.listen_port)),
                                          certfile=self.ssl_crt_path,
                                          keyfile=self.ssl_key_path,
                                          server_side=True),
                        self.handle_request, log=self.request_logger)
        except Exception:
            self.logger.exception('Oops')
            raise


class SADaemon(Daemon):

    def run(self, conf):
        sa = StalkerAgent(conf)
        sa.notify_master()
        while 1:
            try:
                sa.start()
            except Exception as err:
                print err
                eventlet.sleep(5)
