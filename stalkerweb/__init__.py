import eventlet
eventlet.monkey_patch()
from eventlet.green.socket import getfqdn
from flask import Flask
from flask.ext.pymongo import PyMongo
import redis


def _init_redis(app):
    """Initializes Redis client from app config"""

    app.config.setdefault('REDIS_HOST', 'localhost')
    app.config.setdefault('REDIS_PORT', 6379)
    app.config.setdefault('REDIS_DB', 0)
    app.config.setdefault('REDIS_PASSWORD', None)
    return redis.Redis(host=app.config['REDIS_HOST'],
                       port=app.config['REDIS_PORT'],
                       db=app.config['REDIS_DB'],
                       password=app.config['REDIS_PASSWORD'])

app = Flask(__name__, instance_relative_config=False)
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


app.config.from_envvar('STALKERWEB_CONFIG')
mongo = PyMongo(app)
rc = _init_redis(app)

print "== APP CONFIG FOLLOWS =="
for i in app.config:
    print "%s = '%s'" % (i, app.config[i])
print "== END APP CONFIG =="

from stalkerweb import views
