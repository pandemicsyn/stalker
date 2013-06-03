import json
import eventlet
eventlet.monkey_patch()
from eventlet.green import urllib2
from flask import request, abort, jsonify, render_template, session, redirect
import pymongo
from bson import ObjectId
from time import time
from random import choice
from stalkerweb.auth import is_valid_login, login_required, change_pass, remove_user
from stalkerweb import app, mongo, rc
from flask.ext.wtf import Form, Required, TextField, PasswordField, BooleanField
from werkzeug.contrib.cache import RedisCache

VALID_STATES = ['alerting', 'pending', 'in_maintenance', 'suspended']

cache = RedisCache(default_timeout=app.config['CACHE_TTL'])


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
        print err
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
        print "Error while grabbing checks for %s: %s" % (clusterid, err)
        return None


def _get_remote_stats(clusterid):
    target = app.config['GLOBAL_CLUSTERS'][clusterid]['host'] + '/stats'
    headers = {'X-API-KEY': app.config['GLOBAL_CLUSTERS'][clusterid]['key']}
    try:
        req = urllib2.Request(target, headers=headers)
        res = urllib2.urlopen(req, timeout=app.config['REMOTE_TIMEOUT'])
        return json.loads(res.read())
    except Exception as err:
        print "Error while grabbing stats for %s: %s" % (clusterid, err)
        return None


def _get_users_theme(username):
    q = mongo.db.users.find_one({'username': username},
                                {'theme': 1, '_id': False})
    return q.get('theme', 'cerulean')


def _rand_start():
    """Used to randomize the first check (and hopefully stagger
    checks on a single host)"""
    return time() + choice(xrange(300))


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
        if 'args' not in content['checks'][check]:
            return False
        if not isinstance(content['checks'][check]['args'], basestring):
            return False
    # validate roles shoudl just be a list of strings
    for role in content['roles']:
        if not isinstance(role, basestring):
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
                              'pending': False,
                              'status': True, 'in_maintenance': False,
                              'suspended': False, 'out': ''})
        mongo.db.checks.insert(bulk_load)
    except pymongo.errors.DuplicateKeyError as err:
        print err
        abort(400)
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
@app.route("/hosts/<host>")
@login_required
def hosts(host):
    if not host:
        q = [x for x in mongo.db.hosts.find(fields={'_id': False})]
        if q:
            q = {'hosts': q}
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
            abort(500)
    else:
        abort(400)


@app.route('/checks/id/<checkid>/next', methods=['GET', 'POST'])
@login_required
def check_next(checkid):
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
            if request.json['next'] == 'now':
                q = mongo.db.checks.update({'_id': ObjectId(checkid)},
                                           {'$set': {'next': time() - 1}})
            else:
                q = mongo.db.checks.update({'_id': ObjectId(checkid)},
                                           {'$set': {'next': int(request.json['next'])}})
            if q['n'] != 0:
                return jsonify({'success': True})
            else:
                abort(404)
        except (KeyError, ValueError, pymongo.errors.InvalidId):
            abort(400)


@app.route('/checks/id/<checkid>/suspended', methods=['GET', 'POST'])
@login_required
def check_suspended(checkid):
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
            if request.json['suspended'] is True:
                q = mongo.db.checks.update({'_id': ObjectId(checkid)},
                                           {'$set': {'suspended': True}})
            elif request.json['suspended'] is False:
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
    if state == 'alerting':
        q = [x for x in mongo.db.checks.find({'status': False},
                                             fields={'_id': False})]
        if q:
            return jsonify({'alerting': q})
        else:
            return jsonify({'alerting': []})
    elif state == 'pending':
        q = [x for x in mongo.db.checks.find({'pending': True},
                                             fields={'_id': False})]
        if q:
            return jsonify({'pending': q})
        else:
            return jsonify({'pending': []})
    elif state == 'in_maintenance':
        q = [x for x in mongo.db.checks.find({'in_maintenance': True},
                                             fields={'_id': False})]
        if q:
            return jsonify({'in_maintenance': q})
        else:
            return jsonify({'in_maintenance': []})
    elif state == 'suspended':
        q = [x for x in mongo.db.checks.find({'suspended': True},
                                             fields={'_id': False})]
        if q:
            return jsonify({'suspended': q})
        else:
            return jsonify({'suspended': []})
    else:
        abort(400)


@app.route('/global/clusters')
@login_required
def global_clusters():
    return jsonify({'clusters': app.config['GLOBAL_CLUSTERS']})


@app.route('/global/<clusterid>/checks/state/<state>')
@login_required
def global_check_state(clusterid, state):
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
    for i in mongo.db.hosts.find({'$or': [{'hostname': {'$regex': '^%s' % request.args.get('q')}}, {'ip': {'$regex': '^%s' % request.args.get('q')}}]}, fields={'hostname': True, 'ip': True, '_id': False}):
        if i['hostname'].startswith(request.args.get('q')):
            result.append(i['hostname'])
        else:
            result.append(i['ip'])
    print result
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


@app.route('/view/hosts')
@login_required
def view_hosts():
    return render_template('hosts.html')


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
    if state:
        if state in VALID_STATES:
            return render_template('globalstates.html', state=state)
        else:
            abort(404)
    else:
        return render_template('globalstates.html', state='alerting')


@app.route('/signout')
def signout():
    session.pop('logged_in', None)
    return render_template('signout.html')


@app.route('/signin', methods=["GET", "POST"])
def signin():
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

if __name__ == '__main__':
    debug = True
    app.run(host='0.0.0.0', debug=debug)
