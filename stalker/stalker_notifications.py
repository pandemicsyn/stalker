#!/usr/bin/env python

from eventlet.green import urllib, urllib2

from stalker.stalker_utils import get_basic_auth, TRUE_VALUES

try:
    import simplejson as json
except ImportError:
    import json


class PagerDuty(object):
    """Pagerduty Notifications"""

    def __init__(self, conf, logger, redis_client):
        self.conf = conf
        self.logger = logger
        self.rc = redis_client
        self.service_key = conf.get('pagerduty_service_key')
        if not self.service_key:
            raise Exception('No pagerduty service key in conf')
        self.url = conf.get('pagerduty_url', 'https://events.pagerduty.com/generic/2010-04-15/create_event.json')
        self.host_group = conf.get(
            'pagerduty_host_group_alerts', 'n').lower() in TRUE_VALUES

    def _resolve(self, check, incident_key):
        headers = {'Content-Type': 'application/json'}
        data = json.dumps({'service_key': self.service_key,
                           'incident_key': incident_key,
                           'event_type': 'resolve',
                           'description': 'Check %s on %s is UP' % (check['check'],
                                                                    check[
                                                                        'hostname']),
                           'details': check})
        try:
            req = urllib2.Request(self.url, data, headers)
            response = urllib2.urlopen(req)
            result = response.read()
            response.close()
            parsed = json.loads(result[0])
            if 'status' in parsed:
                if parsed['status'] == 'success':
                    self.logger.info('Resolved pagerduty event: %s' % parsed)
                    return True
                else:
                    self.logger.info(
                        'Failed to resolve pagerduty event: %s' % parsed)
                    return False
            else:
                self.logger.info(
                    'Failed to resolve pagerduty event: %s' % parsed)
                return False
        except Exception:
            self.logger.exception('Error resolving pagerduty event.')
            return False

    def _trigger(self, check, incident_key):
        headers = {'Content-Type': 'application/json'}
        data = json.dumps({'service_key': self.service_key,
                           'incident_key': incident_key,
                           'event_type': 'trigger',
                           'description': 'Check %s on %s is DOWN' % (check['check'],
                                                                      check[
                                                                          'hostname']),
                           'details': check})
        try:
            req = urllib2.Request(self.url, data, headers)
            response = urllib2.urlopen(req)
            result = response.read()
            response.close()
            parsed = json.loads(result[0])
            if 'status' in parsed:
                if parsed['status'] == 'success':
                    self.logger.info('Triggered pagerduty event: %s' % parsed)
                    return True
                else:
                    self.logger.info(
                        'Failed to trigger pagerduty event: %s' % parsed)
                    return False
            else:
                self.logger.info(
                    'Failed to trigger pagerduty event: %s' % parsed)
                return False
        except Exception:
            self.logger.exception('Error triggering pagerduty event.')
            return False

    def clear(self, check):
        """Send clear"""
        if self.host_group:
            incident_key = '%s:%s' % (check['hostname'])
        else:
            incident_key = '%s:%s' % (check['hostname'], check['check'])
        track_id = 'pgduty:notified:%s' % incident_key
        notified = self.rc.get(track_id) or 0
        if notified != 0:
            ok = self._resolve(check, incident_key)
            if not ok:
                # TODO: do backup notifications
                pass

    def fail(self, check):
        """Send failure if not already notified"""
        if self.host_group:
            incident_key = '%s:%s' % (check['hostname'])
        else:
            incident_key = '%s:%s' % (check['hostname'], check['check'])
        track_id = 'pgduty:notified:%s' % incident_key
        notified = self.rc.get(track_id) or 0
        if notified == 0:
            ok = self._trigger(check, incident_key)
            if ok:
                self.rc.incr(track_id)
            else:
                # TODO: do backup notifications
                pass
        else:
            self.logger.debug('pagerduty already notified.')


class Mailgun(object):
    """Mailgun Notifications"""

    def __init__(self, conf, logger, redis_client):
        self.conf = conf
        self.logger = logger
        self.rc = redis_client
        self.domain = conf.get('mailgun_domain')
        if not self.domain:
            raise Exception('No mailgun domain in conf.')
        self.api_user = 'api'
        self.api_key = conf.get('mailgun_api_key')
        if not self.api_key:
            raise Exception('No mailgun api key in conf.')
        self.url = 'https://api.mailgun.net/v2/%s/messages' % self.domain
        self.recipients = conf.get('mailgun_recipients')
        if not self.recipients:
            raise Exception('No mailgun recipients in conf.')
        self.basic_auth_creds = get_basic_auth(self.api_user, self.api_key)

    def _send_email(self, check):
        check_name = check['check']
        hostname = check['hostname']
        if check['status'] is True:
            status = 'UP'
        else:
            status = 'DOWN'
        subject = "[stalker] %s on %s is %s" % (check_name, hostname, status)
        data = {"from": "Stalker <stalker@swiftops.mailgun.org>",
                "to": self.recipients,
                "subject": subject,
                "text": "%s" % check}
        headers = {
            'Authorization': 'Basic %s' % self.basic_auth_creds,
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        try:
            post_data = urllib.urlencode(data)
            req = urllib2.Request(self.url, post_data, headers)
            response = urllib2.urlopen(req)
            result = response.read()
            response.close()
            self.logger.info('Mailgun: %s' % result)
        except Exception:
            self.logger.exception('Mailgun notification error.')

    def clear(self, check):
        """Send clear"""
        # TODO: better clear notifications
        incident_key = '%s:%s' % (check['hostname'], check['check'])
        track_id = 'mailgun:notified:%s' % incident_key
        notified = self.rc.get(track_id) or 0
        if notified != 0:
            ok = self._send_email(check)
            self.logger.info('Sent mailgun clear for %s' % track_id)
            if not ok:
                # TODO: do backup notifications
                pass

        pass

    def fail(self, check):
        """Send failure if not already notified"""
        incident_key = '%s:%s' % (check['hostname'], check['check'])
        track_id = 'mailgun:notified:%s' % incident_key
        notified = self.rc.get(track_id) or 0
        if notified == 0:
            ok = self._send_email(check)
            self.logger('Sent mailgun alert for %s' % track_id)
            if ok:
                self.rc.incr(track_id)
            else:
                # TODO: do backup notifications
                pass
        else:
            self.logger.debug('mailgun already notified.')
