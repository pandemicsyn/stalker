import json
import eventlet
eventlet.monkey_patch()
from eventlet.green import urllib2
from flask import request, abort, render_template, session, redirect
from bson import ObjectId
from time import time
from random import randint
from stalkerweb.auth import is_valid_login, login_required, remove_user
from stalkerweb.stutils import jsonify, genPrimaryKey64
from stalkerweb import app, rc, rdb
from flask.ext.wtf import Form
from wtforms import TextField, PasswordField, BooleanField
from wtforms.validators import Required
from werkzeug.contrib.cache import RedisCache
import rethinkdb as r
from rethinkdb.errors import RqlDriverError, RqlRuntimeError
import logging

VALID_STATES = ['alerting', 'pending', 'in_maintenance', 'suspended']

cache = RedisCache(host=app.config['REDIS_HOST'], port=app.config['REDIS_PORT'], default_timeout=app.config['CACHE_TTL'])

logger = logging.getLogger(app.config['LOG_NAME'])


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
    q = list(r.table("users").filter({"username": username}).pluck({"theme": True}).run(rdb.conn))[0]
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
    ip_addr = request.json.get('ip', request.remote_addr)
    if ip_addr == '':
        ip_addr = request.remote_addr
    try:
        pkey = genPrimaryKey64("%s%s" % (hid, ip_addr))
        q = r.table("hosts").insert({
                "id": pkey,
                "hostname": hid,
                "ip": ip_addr,
                "checks": checks,
                "roles": roles
            },conflict="update").run(rdb.conn)
        q = r.table("checks").filter({"hostname": hid}).delete().run(rdb.conn) #we're about to reinstart all so just delete all incase checks got removed
        bulk_load = []
        for i in checks:
            bulk_load.append({'id': genPrimaryKey64("%s%s%s" % (hid, ip_addr, i)),
                              'hostname': hid, 'ip': ip_addr,
                              'check': i, 'last': 0, 'next': _rand_start(),
                              'interval': checks[i]['interval'],
                              'follow_up': checks[i]['follow_up'],
                              'pending': False,
                              'status': None, 'in_maintenance': False,
                              'suspended': False, 'out': '',
                              'priority': checks[i].get('priority', 1)})
            q = r.table("checks").insert(bulk_load, conflict="update").run(rdb.conn)
    except Exception as err:
        logger.error(err)
        return jsonify({'status': 'fail', 'error': str(err)}), 400
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
        q = list(r.table("users").filter({"username": username}).without("hash").run(rdb.conn))[0]
        if q:
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
        q = r.table("users").filter({"username": username}).update(fields).run(rdb.conn) 
        if q["replaced"] != 0 :
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
        q = list(r.table("hosts").without("id").run(rdb.conn))
        if q:
            q = {'hosts': q}
    else:
        if request.method == 'DELETE':
            q = r.table("checks").filter((r.row["hostname"] == host) | (r.row["ip"] == host)).delete().run(rdb.conn)
            q = r.table("hosts").filter((r.row["hostname"] == host) | (r.row["ip"] == host)).delete().run(rdb.conn)
            return jsonify({'success': True})
        else:
            q = list(r.table("hosts").filter((r.row["hostname"] == host) | (r.row["ip"] == host)).without("id").run(rdb.conn))
    if q:
        return jsonify(q[0])
    else:
        abort(404)


@app.route("/checks/", defaults={'host': None})
@app.route("/checks/host/<host>")
@login_required
def checks(host):
    """Get all checks for a given hostname or ip"""
    if not host:
        q = list(r.table("checks").run(rdb.conn))
    else:
        q = list(r.table("checks").filter((r.row["hostname"] == host) | (r.row["ip"] == host)).run(rdb.conn))
    if q:
        for check in q:
            check['id'] = str(check['id'])
        return jsonify({'checks': q})
    else:
        abort(404)


@app.route('/checks/id/<checkid>', methods=['GET', 'DELETE'])
@login_required
def checks_by_id(checkid):
    """Get info for or delete a given check"""
    if request.method == 'GET':
        check = r.table("checks").get(checkid).run(rdb.conn)
        if check:
            check['id'] = str(check['id'])
            return jsonify({'check': check})
        else:
            abort(404)
    elif request.method == 'DELETE':
        q = r.table("checks").get(checkid).delete().run(rdb.conn)
        if q["deleted"] == 1:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False})


@app.route('/checks/id/<checkid>/owner', methods=['GET', 'POST', 'DELETE'])
@login_required
def check_owner(checkid):
    """claim or unclaim a given check"""
    if request.method == 'GET':
        check = r.table("checks").get(checkid).run(rdb.conn)
        if check:
            check['id'] = str(check['id'])
            return jsonify({'check': check})
        else:
            abort(404)
    elif request.method == 'POST':
        if not request.json:
            abort(400)
        try:
            if request.json.get('owner'):
                q = r.table("checks").get(checkid).update({"owner": str(request.json["owner"])}).run(rdb.conn)
            else:
                abort(400)
            if q["replaced"] != 0:
                return jsonify({'success': True})
            else:
                abort(404)
        except Exception as err:
            logger.error(err)
            abort(400)
    elif request.method == 'DELETE':
        try:
            q = r.table("checks").get(checkid).update({"owner": ""}).run(rdb.conn)
            if q["replaced"] != 0:
                return jsonify({'success': True})
            else:
                abort(404)
        except Exception as err:
            logger.error(err)
            abort(400)


@app.route('/checks/id/<checkid>/next', methods=['GET', 'POST'])
@login_required
def check_next(checkid):
    """Reschedule a given check"""
    if request.method == 'GET':
        check = r.table("checks").get(checkid).run(rdb.conn)
        if check:
            check['id'] = str(check['id'])
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
                q = r.table("checks").get(checkid).update({"next": time() - 1}).run(rdb.conn)
            else:
                q = r.table("checks").get(checkid).update({"next": int(request.json["next"])}).run(rdb.conn)
            if q["replaced"] != 0:
                return jsonify({'success': True})
            else:
                abort(404)
        except Exception as err:
            logger.error(err)
            abort(400)


@app.route('/checks/id/<checkid>/suspended', methods=['GET', 'POST'])
@login_required
def check_suspended(checkid):
    """Suspend a given check"""
    if request.method == 'GET':
        check = r.table("checks").get(checkid).run(rdb.conn)
        if check:
            check['id'] = str(check['id'])
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
                q = r.table("checks").get(checkid).update({"suspended": True}).run(rdb.conn)
            elif request.json.get('suspended') is False:
                q = r.table("checks").get(checkid).update({"suspended": False}).run(rdb.conn)
            else:
                abort(400)
            if q['replaced'] != 0:
                return jsonify({'success': True})
            else:
                abort(404)
        except Exception as err:
            logger.error(err)
            abort(400)


@app.route('/checks/state/<state>')
@login_required
def check_state(state):
    """List of checks in cluster in a given state [alerting/pending/suspended]"""
    if state == 'alerting':
        q = list(r.table("checks").get_all(False, index="status").run(rdb.conn))
        if q:
            return jsonify({'alerting': q})
        else:
            return jsonify({'alerting': []})
    elif state == 'pending':
        q = list(r.table("checks").get_all(True, index="pending").run(rdb.conn))
        if q:
            return jsonify({'pending': q})
        else:
            return jsonify({'pending': []})
    elif state == 'in_maintenance':
        q = list(r.table("checks").get_all(True, index="in_maintenance").run(rdb.conn))
        if q:
            return jsonify({'in_maintenance': q})
        else:
            return jsonify({'in_maintenance': []})
    elif state == 'suspended':
        q = list(r.table("checks").get_all(True, index="suspended").run(rdb.conn))
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
        log = list(r.table("state_log").filter({"hostname": hostname, "check": checkname}).order_by(r.desc("last")).limit(limit).run(rdb.conn))
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
        notes = list(r.table("notes").filter({"hostname": hostname}).order_by(r.desc("ts")).limit(limit).run(rdb.conn))
        if notes:
            return jsonify({'notes': sorted(notes, key=lambda k: k['ts'])})
        else:
            abort(404)
    elif request.method == 'POST':
        if not request.json:
            abort(400)
        if not request.json.get("user") or not request.json.get("note"):
            abort(400)
        if not r.table("hosts").get_all(hostname, index="hostname").run(rdb.conn):
            abort(404)
        alerting = [x["check"] for x in r.table("checks").filter({"h stname": hostname, "status": False}).run(rdb.conn)]
        q = r.table("notes").insert({'hostname': hostname, 'user': request.json.get("user"),
                                     'note': request.json.get("note"), 'ts': time(), 'alerting': alerting}).run(rdb.conn)
        if q["inserted"] == 1:
            return jsonify({'success': True})
        else:
            logger.error(q)
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
    for i in r.table("hosts").filter(
            r.row["hostname"].match("^%s" % request.args.get('q')) | r.row["ip"].match("^%s" % request.args.get('q'))
            ).pluck({"hostname": True, "ip": True}).run(rdb.conn):
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
            func_list[rule.rule] = app.view_functions[rule.endpoint].__doc__
    return jsonify(func_list)


if __name__ == '__main__':
    debug = True
    app.run(host='0.0.0.0', debug=debug)
