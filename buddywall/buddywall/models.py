from google.appengine.ext import db
from google.appengine.ext.db import run_in_transaction
from ragendja.auth.models import User
import random

BORDER_STYLES = ['solid', 'dashed', 'dotted', 'double']
GENDERS = [0,1]

class XnUser(User):
    uid = db.StringProperty(required=True)
    selected_uids = db.StringListProperty()
    bg_color = db.StringProperty()
    bg_style = db.IntegerProperty(default=0)
    border_style = db.StringProperty(choices=BORDER_STYLES)
    border_color = db.StringListProperty()
    wall_name = db.StringProperty()
    max_friends = db.IntegerProperty()
    num_invited = db.IntegerProperty(default=0)
    app_users = db.StringListProperty()
    
    sex = db.IntegerProperty(choices=GENDERS)
    birth_year = db.StringProperty()
    birth_month = db.StringProperty()
    birth_day = db.StringProperty()
    home_country = db.StringProperty()
    home_province = db.StringProperty()
    home_city = db.StringProperty()
    head_url = db.LinkProperty()
    
    @classmethod
    def get_or_insert_ex(cls, key_name, **kwds):
        def txn():
            entity = cls.get_by_key_name(key_name, parent=kwds.get('parent'))
            if entity is None:
                entity = cls(key_name=key_name, **kwds)
                entity.put()
                return (entity, True)
            return (entity, False)
        return run_in_transaction(txn)
    
    @staticmethod
    def get_or_insert_by_uid(uid, **kwargs):
        key_name = 'uid:'+uid
        return XnUser.get_or_insert_ex(key_name, uid=uid, **kwargs)

SHARDS_PER_COUNTER = 20

class CounterShard(db.Model):
    name = db.StringProperty(required=True)
    count = db.IntegerProperty(default=0)

def get_count(counter_name):
    result = 0
    for shard in CounterShard.gql('WHERE name=:1', counter_name):
        result += shard.count
    return result

def change_count(counter_name, delta):
    shard_id = '/%s/%s' % (
                           counter_name, random.randint(1, SHARDS_PER_COUNTER))
    def update():
        shard = CounterShard.get_by_key_name(shard_id)
        if shard:
            shard.count += delta
        else:
            shard = CounterShard(
                                 key_name=shard_id, name=counter_name, count=delta)
        shard.put()
    db.run_in_transaction(update)