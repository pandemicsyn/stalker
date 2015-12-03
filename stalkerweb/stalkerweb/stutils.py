from flask import Flask, Response
from werkzeug.routing import BaseConverter, ValidationError
from base64 import urlsafe_b64encode, urlsafe_b64decode
from bson.objectid import ObjectId
from bson.errors import InvalidId
import datetime
import mmh3

try:
    import json
except ImportError:
    import simplejson as json

try:
    from bson.objectid import ObjectId
except:
    pass


class APIEncoder(json.JSONEncoder):

    def default(self, obj):
        if isinstance(obj, (datetime.datetime, datetime.date)):
            return obj.ctime()
        elif isinstance(obj, datetime.time):
            return obj.isoformat()
        elif isinstance(obj, ObjectId):
            return str(obj)
        return json.JSONEncoder.default(self, obj)


def jsonify(data):
    return Response(json.dumps(data, cls=APIEncoder),
                    mimetype='application/json')


class ObjectIDConverter(BaseConverter):

    def to_python(self, value):
        try:
            return ObjectId(urlsafe_b64decode(value))
        except (InvalidId, ValueError, TypeError):
            raise ValidationError()

    def to_url(self, value):
        return urlsafe_b64encode(value.binary)

# make mmh3 compat with go's murmur3 impl


def genPrimaryKey64(data):
    return "%x" % (mmh3.hash128(data) & 0xFFFFFFFFFFFFFFFF)
