import json
import eventlet
eventlet.monkey_patch()
from eventlet.green import urllib2
from flask import request, abort, render_template, session, redirect
import pymongo
from bson import ObjectId
from time import time
from random import randint
from stalkerweb.auth import is_valid_login, login_required, remove_user
from stalkerweb.stutils import jsonify
from stalkerweb import app, mongo, rc
from stalker.stalker_utils import get_logger
from flask.ext.wtf import Form, Required, TextField, PasswordField, \
    BooleanField
from werkzeug.contrib.cache import RedisCache

VALID_STATES = ['alerting', 'pending', 'in_maintenance', 'suspended']

cache = RedisCache(default_timeout=app.config['CACHE_TTL'])

logger = get_logger(app.config['LOG_NAME'],
                    log_path=app.config['LOG_FILE'],
                    count=app.config['LOG_COUNT'])


class SignInForm(Form):
    username = TextField(validators=[Required()])
    password = PasswordField(validators=[Required()])
    remember_me = BooleanField()


def _get_local_metrics():
    metrics = {}
    mkeys = ['checks', 'failing', 'flapping', 'pending', 'qsize',
             'suspended']
    try:
        values = rc.mget(mkeys)
        for k in mkeys:
            metrics[k] = int(values[mkeys.index(k)])
        return metrics
    except Exception as err:
        logger.exception('Error gathering metrics')
        return None


def _get_remote_checks(clusterid, state):
    endpoints = {'alerting': '/checks/state/alerting',
                 'pending': '/checks/state/pending',
                 'suspended': '/checks/state/suspended',
                 'in_maintenance': '/checks/state/in_maintenance'}
    target = app.config['GLOBAL_CLUSTERS'][clusterid]['host'] + \
        endpoints[state]
    headers = {'X-API-KEY': app.config['GLOBAL_CLUSTERS'][clusterid]['key']}
    try:
        req = urllib2.Request(target, headers=headers)
        res = urllib2.urlopen(req, timeout=app.config['REMOTE_TIMEOUT'])
        return json.loads(res.read())
    except Exception as err:
        logger.exception("Error grabbing checks for %s: %s" % (clusterid, err))
        return None


def _get_remote_stats(clusterid):
    target = app.config['GLOBAL_CLUSTERS'][clusterid]['host'] + '/stats'
    headers = {'X-API-KEY': app.config['GLOBAL_CLUSTERS'][clusterid]['key']}
    try:
        req = urllib2.Request(target, headers=headers)
        res = urllib2.urlopen(req, timeout=app.config['REMOTE_TIMEOUT'])
        return json.loads(res.read())[clusterid]
    except Exception as err:
        logger.exception("Error grabbing stats for %s: %s" % (clusterid, err))
        return None


def _get_users_theme(username):
    q = mongo.db.users.find_one({'username': username},
                                {'theme': 1, '_id': False})
    return q.get('theme', 'cerulean')


def _rand_start():
    """Used to randomize the first check (and hopefully stagger
    checks on a single host)"""
    return time() + randint(1, 600)


def _valid_registration(content):
    fields = [('hostname', basestring), ('checks', dict), ('roles', list)]
    for field in fields:
        if field[0] in content:
            if not isinstance(content[field[0]], field[1]):
                return False
        else:
            return False
    # validate checks each should have a interval and args field
    for check in content['checks']:
        if not isinstance(content['checks'][check], dict):
            return False
        if 'interval' not in content['checks'][check]:
            return False
        if not isinstance(content['checks'][check]['interval'], int):
            return False
        if not isinstance(content['checks'][check]['follow_up'], int):
            return False
        if 'args' not in content['checks'][check]:
            return False
        if 'priority' in content['checks'][check]:
            if not isinstance(content['checks'][check]['priority'], int):
                return False
        if not isinstance(content['checks'][check]['args'], basestring):
            return False
    # everything checked out
    return True


@app.route("/register", methods=['POST', 'PUT'])
def register():
    if request.headers.get('X-REGISTER-KEY') != app.config['REGISTER_KEY']:
        abort(412)
    if not request.json:
        abort(400)
    if not _valid_registration(request.json):
        abort(400)
    hid = request.json['hostname']
    checks = request.json['checks']
    roles = request.json['roles']
    try:
        # TODO: need a unique constraint on hostname
        q = mongo.db.hosts.update({'hostname': hid},
                                  {"$set": {'hostname': hid,
                                            'ip': request.remote_addr,
                                            'checks': checks, 'roles': roles}},
                                  upsert=True)
        # TODO: Since this is just a POC we'll just blow away ALL of the
        # existing checks for the host and readd them.
        mongo.db.checks.remove({'hostname': hid})
        bulk_load = []
        for i in checks:
            bulk_load.append({'hostname': hid, 'ip': request.remote_addr,
                              'check': i, 'last': 0, 'next': _rand_start(),
                              'interval': checks[i]['interval'],
                              'follow_up': checks[i]['follow_up'],
                              'pending': False,
                              'status': None, 'in_maintenance': False,
                              'suspended': False, 'out': '',
                              'priority': checks[i].get('priority', 1)})
        mongo.db.checks.insert(bulk_load)
    except pymongo.errors.DuplicateKeyError as err:
        logger.error(err)
        return jsonify({'status': 'fail', 'error': err}), 400
    return jsonify({'status': 'ok'})


@app.route("/user/", defaults={'username': None})
@app.route("/user/<username>", methods=['GET', 'POST', 'DELETE'])
@login_required
def users(username):
    if not username:
        if request.method == 'DELETE':
            abort(400)  # don't allow deletes with out user
        if session.get('username', False):
            username = session.get('username')
        else:
            abort(400)
    if request.method == 'GET':
        q = mongo.db.users.find_one({'username': username}, {'hash': False})
        if q:
            q['_id'] = str(q['_id'])
            if 'theme' not in q:
                q['theme'] = 'cerulean'
            return jsonify(q)
        else:
            abort(404)
    elif request.method == 'DELETE':
        return jsonify({'success': remove_user(username)})
    elif request.method == 'POST':
        fields = {}
        if not request.json:
            abort(400)
        if 'theme' in request.json:
            if request.json['theme'] in app.config['THEMES']:
                fields['theme'] = request.json['theme']
            else:
                abort(400)
        if 'email' in request.json:
            fields['email'] = request.json['email']
        q = mongo.db.users.update({'username': username},
                                  {"$set": fields}, upsert=False)
        if q:
            if session and 'theme' in fields:
                session['theme'] = fields['theme']
            return jsonify({'success': True})
        else:
            return jsonify({'success': False})


@app.route("/hosts/", defaults={'host': None})
@app.route("/hosts/<host>", methods=['GET', 'DELETE'])
@login_required
def hosts(host):
    """Delete a given host and all its checks"""
    if not host:
        q = [x for x in mongo.db.hosts.find(fields={'_id': False})]
        if q:
            q = {'hosts': q}
    else:
        if request.method == 'DELETE':
            try:
                q = mongo.db.checks.remove({'$or': [{'hostname': host},
                                                    {'ip': host}]}, safe=True)
                q = mongo.db.hosts.remove({'$or': [{'hostname': host},
                                                   {'ip': host}]}, safe=True)
                return jsonify({'success': True})
            except pymongo.errors.InvalidId:
                abort(404)
            except pymongo.errors.OperationFailure:
                logger.exception('Error removing hosts/checks.')
                abort(500)
        else:
            q = mongo.db.hosts.find_one({'$or': [{'hostname': host},
                                                 {'ip': host}]},
                                        fields={'_id': False})
    if q:
        return jsonify(q)
    else:
        abort(404)


@app.route("/checks/", defaults={'host': None})
@app.route("/checks/host/<host>")
@login_required
def checks(host):
    """Get all checks for a given hostname or ip"""
    if not host:
        q = [x for x in mongo.db.checks.find()]
    else:
        q = [x for x in mongo.db.checks.find({'$or': [{'hostname': host},
                                                      {'ip': host}]})]
    if q:
        for check in q:
            check['_id'] = str(check['_id'])
        return jsonify({'checks': q})
    else:
        abort(404)


@app.route('/checks/id/<checkid>', methods=['GET', 'DELETE'])
@login_required
def checks_by_id(checkid):
    """Get info for or delete a given check"""
    if request.method == 'GET':
        check = mongo.db.checks.find_one({'_id': ObjectId(checkid)})
        if check:
            check['_id'] = str(check['_id'])
            return jsonify({'check': check})
        else:
            abort(404)
    elif request.method == 'DELETE':
        try:
            q = mongo.db.checks.remove({'_id': ObjectId(checkid)}, safe=True)
            return jsonify({'success': True})
        except pymongo.errors.InvalidId:
            abort(404)
        except pymongo.errors.OperationFailure:
            logger.exception('Error removing check')
            abort(500)


@app.route('/checks/id/<checkid>/owner', methods=['GET', 'POST', 'DELETE'])
@login_required
def check_owner(checkid):
    """claim or unclaim a given check"""
    if request.method == 'GET':
        check = mongo.db.checks.find_one({'_id': ObjectId(checkid)},
                                         {'owner': 1})
        if check:
            check['_id'] = str(check['_id'])
            return jsonify({'check': check})
        else:
            abort(404)
    elif request.method == 'POST':
        if not request.json:
            abort(400)
        try:
            if request.json.get('owner'):
                q = mongo.db.checks.update({'_id': ObjectId(checkid)},
                                           {'$set': {'owner': str(request.json['owner'])}})
            else:
                abort(400)
            if q['n'] != 0:
                return jsonify({'success': True})
            else:
                abort(404)
        except (KeyError, ValueError, pymongo.errors.InvalidId) as err:
            logger.error(err)
            abort(400)
    elif request.method == 'DELETE':
        try:
            q = mongo.db.checks.update({'_id': ObjectId(checkid)},
                                       {'$set': {'owner': ''}})
            if q['n'] != 0:
                return jsonify({'success': True})
            else:
                abort(404)
        except (KeyError, ValueError, pymongo.errors.InvalidId) as err:
            logger.error(err)
            abort(400)


@app.route('/checks/id/<checkid>/next', methods=['GET', 'POST'])
@login_required
def check_next(checkid):
    """Reschedule a given check"""
    if request.method == 'GET':
        check = mongo.db.checks.find_one({'_id': ObjectId(checkid)},
                                         {'next': 1})
        if check:
            check['_id'] = str(check['_id'])
            return jsonify({'check': check})
        else:
            abort(404)
    elif request.method == 'POST':
        if not request.json:
            abort(400)
        try:
            if not request.json.get('next'):
                abort(400)
            if request.json.get('next') == 'now':
                q = mongo.db.checks.update({'_id': ObjectId(checkid)},
                                           {'$set': {'next': time() - 1}})
            else:
                q = mongo.db.checks.update({'_id': ObjectId(checkid)},
                                           {'$set': {'next': int(request.json['next'])}})
            if q['n'] != 0:
                return jsonify({'success': True})
            else:
                abort(404)
        except (KeyError, ValueError, pymongo.errors.InvalidId) as err:
            logger.error(err)
            abort(400)


@app.route('/checks/id/<checkid>/suspended', methods=['GET', 'POST'])
@login_required
def check_suspended(checkid):
    """Suspend a given check"""
    if request.method == 'GET':
        check = mongo.db.checks.find_one({'_id': ObjectId(checkid)},
                                         {'suspended': 1})
        if check:
            check['_id'] = str(check['_id'])
            return jsonify({'check': check})
        else:
            abort(404)
    elif request.method == 'POST':
        if not request.json:
            abort(400)
        try:
            if not request.json.get('suspended'):
                abort(400)
            if request.json.get('suspended') is True:
                q = mongo.db.checks.update({'_id': ObjectId(checkid)},
                                           {'$set': {'suspended': True}})
            elif request.json.get('suspended') is False:
                q = mongo.db.checks.update({'_id': ObjectId(checkid)},
                                           {'$set': {'suspended': False}})
            else:
                abort(400)
            if q['n'] != 0:
                return jsonify({'success': True})
            else:
                abort(404)
        except (KeyError, ValueError, pymongo.errors.InvalidId):
            abort(400)


@app.route('/checks/state/<state>')
@login_required
def check_state(state):
    """List of checks in cluster in a given state [alerting/pending/suspended]"""
    if state == 'alerting':
        q = [x for x in mongo.db.checks.find({'status': False})]
        if q:
            return jsonify({'alerting': q})
        else:
            return jsonify({'alerting': []})
    elif state == 'pending':
        q = [x for x in mongo.db.checks.find({'pending': True})]
        if q:
            return jsonify({'pending': q})
        else:
            return jsonify({'pending': []})
    elif state == 'in_maintenance':
        q = [x for x in mongo.db.checks.find({'in_maintenance': True})]
        if q:
            return jsonify({'in_maintenance': q})
        else:
            return jsonify({'in_maintenance': []})
    elif state == 'suspended':
        q = [x for x in mongo.db.checks.find({'suspended': True})]
        if q:
            return jsonify({'suspended': q})
        else:
            return jsonify({'suspended': []})
    else:
        abort(400)


@app.route('/state_log/<hostname>/<checkname>', methods=['GET'])
@login_required
def state_log_by_check(hostname, checkname):
    """Get check history for a given check on a given host"""
    if request.method == 'GET':
        try:
            limit = request.args.get('limit', 10, type=int)
        except ValueError:
            abort(400)
        log = [x for x in mongo.db.state_log.find({'hostname': hostname, 'check': checkname}, limit=limit).sort('last', pymongo.DESCENDING)]
        if log:
            return jsonify({'state_log': sorted(log, key=lambda k: k['last'])})
        else:
            abort(404)
    else:
        abort(400)


@app.route('/notes/<hostname>', methods=['GET', 'POST'])
@login_required
def list_notes(hostname):
    """Retrieve a list of notes associated with a host. Or given
      {'user': 'username', 'note': 'some message'} post a note."""
    if request.method == 'GET':
        try:
            #someday i should probably add offset support here and in the statelog
            limit = request.args.get('limit', 50, type=int)
        except ValueError:
            abort(400)
        notes = [x for x in mongo.db.notes.find({'hostname': hostname}, limit=limit).sort('ts', pymongo.DESCENDING)]
        if notes:
            return jsonify({'notes': sorted(notes, key=lambda k: k['ts'])})
        else:
            abort(404)
    elif request.method == 'POST':
        if not request.json:
            abort(400)
        if not request.json.get("user") or not request.json.get("note"):
            abort(400)
        if not mongo.db.hosts.find_one({'$or': [{'hostname': hostname}]}):
            abort(404)
        alerting = [x['check'] for x in mongo.db.checks.find({'hostname': hostname, 'status': False})]
        q = mongo.db.notes.insert({'hostname': hostname,
                                   'user': request.json.get("user"),
                                   'note': request.json.get("note"),
                                   'ts': time(), 'alerting': alerting})
        if q:
            return jsonify({'success': True})
        else:
            abort(500)
    else:
        abort(400)
    

@app.route('/global/clusters')
@login_required
def global_clusters():
    """List of known clusters and their id"""
    return jsonify({'clusters': app.config['GLOBAL_CLUSTERS']})


@app.route('/global/<clusterid>/checks/state/<state>')
@login_required
def global_check_state(clusterid, state):
    """Get a list of all checks in provided state for a given cluster"""
    if clusterid not in app.config['GLOBAL_CLUSTERS']:
        abort(400)
    if state in VALID_STATES:
        ckey = '%s:%s' % (clusterid, state)
        cached = cache.get(ckey)
        if cached:
            return jsonify({clusterid: cached})
        else:
            q = _get_remote_checks(clusterid, state)
        if q:
            cache.set(ckey, q)
            return jsonify({clusterid: q})
        else:
            abort(500)
    else:
        abort(400)


@app.route('/stats', defaults={'clusterid': None})
@app.route('/stats/<clusterid>')
@login_required
def stalker_stats(clusterid):
    """Obtain stats for this cluster or one with a given clusterid"""
    default = {'qsize': None, 'failing': None, 'flapping': None,
               'suspended': None, 'checks': None, 'pending': None}
    if not clusterid:
        q = _get_local_metrics()
        if q:
            return jsonify({app.config['LOCAL_CID']: q})
        else:
            return jsonify({app.config['LOCAL_CID']: default})
    else:
        if clusterid in app.config['GLOBAL_CLUSTERS']:
            ckey = '%s:%s' % (clusterid, 'stats')
            cached = cache.get(ckey)
            if cached:
                return jsonify({clusterid: cached})
            else:
                q = _get_remote_stats(clusterid)
                if q:
                    cache.set(ckey, q)
                    return jsonify({clusterid: q})
                else:
                    return jsonify({clusterid: default})
        elif clusterid == 'all':
            q = {}
            q[app.config['LOCAL_CID']] = _get_local_metrics()
            for cid in app.config['GLOBAL_CLUSTERS'].keys():
                ckey = '%s:%s' % (cid, 'stats')
                cached = cache.get(ckey)
                if cached:
                    q[cid] = cached
                else:
                    q[cid] = _get_remote_stats(cid)
                    if not q[cid]:
                        q[cid] = default
                    cache.set(ckey, q[cid])
            return jsonify({'all': q})
        else:
            abort(404)


@app.route('/findhost')
@login_required
def findhost():
    """Just used for the type ahead"""
    # probably should cache hosts in memcached/redis for type ahead crap
    if not request.args.get('q'):
        abort(400)
    result = []
    for i in mongo.db.hosts.find({'$or': [{'hostname': {'$regex': '^%s' % request.args.get('q')}},
                                          {'ip': {'$regex': '^%s' % request.args.get('q')}}]},
                                 fields={'hostname': True, 'ip': True,
                                         '_id': False}):
        if i['hostname'].startswith(request.args.get('q')):
            result.append(i['hostname'])
        else:
            result.append(i['ip'])
    return ",".join(result)


@app.route('/')
@login_required
def index():
    return render_template('states.html', state='alerting')


@app.route('/view/states', defaults={'state': None})
@app.route('/view/states/<state>')
@login_required
def view_states(state):
    if state:
        if state in VALID_STATES:
            return render_template('states.html', state=state)
        else:
            abort(404)
    else:
        return render_template('states.html', state='alerting')


@app.route('/view/checks')
@login_required
def view_checks():
    return render_template('allchecks.html')


@app.route('/view/host/', defaults={'hostname': None})
@app.route('/view/host/<hostname>')
@login_required
def view_single_host(hostname):
    if request.args.get('search'):
        hostname = request.args.get('search')
    if not hostname:
        abort(404)
    else:
        return render_template('host.html', target=hostname)


@app.route('/view/user/<username>')
@login_required
def view_user(username):
    return render_template('user.html')


@app.route('/global/view/states', defaults={'state': None})
@app.route('/global/view/states/<state>/')
@login_required
def view_global(state):
    """Global view of provided state [alerting/pending/suspended]"""
    if state:
        if state in VALID_STATES:
            return render_template('globalstates.html', state=state)
        else:
            abort(404)
    else:
        return render_template('globalstates.html', state='alerting')


@app.route('/signout')
def signout():
    """Sign out"""
    session.pop('logged_in', None)
    return render_template('signout.html')


@app.route('/signin', methods=["GET", "POST"])
def signin():
    """Sign in"""
    form = SignInForm()
    if form.validate_on_submit():
        username = form.username.data.strip()
        password = form.password.data.strip()
        if is_valid_login(username, password):
            session['theme'] = _get_users_theme(username)
            session['logged_in'] = True
            session['username'] = username
            if form.remember_me.data:
                session.permanent = True
            else:
                session.permanent = False
            if request.args.get('next') == 'signin':
                return redirect("/")
            else:
                return redirect(request.args.get('next') or request.referrer or "/")
        else:
            return render_template('signin.html', form=form, error="Failed")
    return render_template('signin.html', form=form, error=None)


@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


@app.route('/routes/list', methods=['GET'])
@login_required
def help():
    """Show endpoints"""
    func_list = {}
    for rule in app.url_map.iter_rules():
        if rule.endpoint != 'static':
            #print app.view_functions[rule.endpoint].__globals__
            func_list[rule.rule] = app.view_functions[rule.endpoint].__doc__
    return jsonify(func_list)


if __name__ == '__main__':
    debug = True
    app.run(host='0.0.0.0', debug=debug)
