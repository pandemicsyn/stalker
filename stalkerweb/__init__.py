import eventlet
eventlet.monkey_patch()
from eventlet.green.socket import getfqdn
from flask.ext.pymongo import PyMongo
from flask import Flask
import redis
from stalkerweb.stutils import ObjectIDConverter
from stalker.stalker_utils import get_logger
from flask_rethinkdb import RethinkDB



def _init_redis(app):
    """Initializes Redis client from app config."""

    app.config.setdefault('REDIS_HOST', 'localhost')
    app.config.setdefault('REDIS_PORT', 6379)
    app.config.setdefault('REDIS_DB', 0)
    app.config.setdefault('REDIS_PASSWORD', None)
    return redis.Redis(host=app.config['REDIS_HOST'],
                       port=app.config['REDIS_PORT'],
                       db=app.config['REDIS_DB'],
                       password=app.config['REDIS_PASSWORD'])

app = Flask(__name__, instance_relative_config=False)

app.url_map.converters['objectid'] = ObjectIDConverter


app.config["RETHINKDB_HOST"] = "172.17.0.31"
app.config["RETHINKDB_PORT"] = "28015"
app.config["RETHINKDB_AUTH"] = "password"
app.config["RETHINKDB_DB"] = "stalkerweb"
app.config['MONGO_DBNAME'] = 'stalkerweb'
app.config['LOCAL_CID'] = getfqdn()
app.config['MONGO_USERNAME'] = None
app.config['MONGO_PASSWORD'] = None
app.config['GLOBAL_CLUSTERS'] = None
app.config['REMOTE_TIMEOUT'] = 2
app.config['REGISTER_KEY'] = 'itsamario'
app.config['API_KEY'] = 'something'
app.config['SECRET_KEY'] = 'SuperSecretDevKeyChangeMe!'
app.config['THEMES'] = ['cosmo', 'cerulean', 'cyborg', 'slate', 'spacelab',
                        'united', 'flatly']
app.config['CACHE_TTL'] = 10
app.config['GRAPHITE_ENABLE'] = False
app.config['GRAPHITE_HOST'] = 'http://localhost/'
app.config['LOG_FILE'] = '/var/log/stalker/stalkerweb.log'
app.config['LOG_NAME'] = 'stalkerweb'
app.config['LOG_COUNT'] = 7

app.config.from_envvar('STALKERWEB_CONFIG')

mongo = PyMongo(app)
rc = _init_redis(app)
rdb = RethinkDB(app)

print "== APP CONFIG FOLLOWS =="
for i in app.config:
    print "%s = '%s'" % (i, app.config[i])
print "== END APP CONFIG =="

from stalkerweb import views


