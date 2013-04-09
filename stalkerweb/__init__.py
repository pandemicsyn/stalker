from flask import Flask
from flask.ext.pymongo import PyMongo

app = Flask(__name__, instance_relative_config=True)
app.config['MONGO_DBNAME'] = 'stalkerweb'
app.config['REGISTER_KEY'] = 'itsamario'
app.config['API_KEY'] = 'something'
app.config['SECRET_KEY'] = 'SuperSecretDevKeyChangeMe!'
app.config['THEMES'] = ['cosmo', 'cerulean', 'cyborg', 'slate', 'spacelab', 'united']
mongo = PyMongo(app)

from stalkerweb import views
