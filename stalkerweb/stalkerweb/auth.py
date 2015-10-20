from flask.ext.bcrypt import generate_password_hash, check_password_hash
from flask import request, redirect, url_for, session, abort
from functools import wraps
from stalkerweb import rdb, app
from stalkerweb.stutils import genPrimaryKey64
import rethinkdb as r


def is_valid_email_login(email, password):
    uinfo = list(r.table("users").filter({"email": email}).run(rdb.conn))
    if len(uinfo) != 1:
        return False
    else:
        if check_password_hash(uinfo[0]['hash'], password):
            return True
        else:
            return False


def is_valid_login(username, password):
    uinfo = list(r.table("users").get_all(
        username, index="username").run(rdb.conn))
    if len(uinfo) != 1:
        return False
    else:
        if check_password_hash(uinfo[0]['hash'], password):
            return True
        else:
            return False


def add_user(username, password, email):
    pw_hash = generate_password_hash(password)
    try:
        res = r.table("users").insert({'id': genPrimaryKey64("%s%s" % (
            username, email)), 'username': username, 'hash': pw_hash, 'email': email}).run(rdb.conn)
        if res["inserted"] == 1:
            return True
        else:
            return False
    except Exception:
        return False


def change_pass(username, email, password):
    pw_hash = generate_password_hash(password)
    try:
        q = r.table("users").get(genPrimaryKey64("%s%s" % (username, email))).update(
            {"hash": pw_hash}).run(rdb.conn)
        if q["replaced"]:
            return True
        else:
            return False
    except Exception as err:
        print err
        return False


def remove_user(username, email):
    try:
        q = r.table("users").get(
            genPrimaryKey64("%s%s" % (username, email))).delete().run(rdb.conn)
        if q["deleted"] == 1:
            return True
        else:
            return False
    except Exception as err:
        print err
        return False


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not request.headers.get('X-API-KEY'):
            if not session.get('logged_in', False):
                return redirect(url_for('signin', next=request.url))
            return f(*args, **kwargs)
        else:
            if request.headers.get('X-API-KEY') == app.config['API_KEY']:
                return f(*args, **kwargs)
            else:
                abort(403)
    return decorated_function
