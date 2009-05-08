from google.appengine.ext import db
from google.appengine.ext.db import run_in_transaction
from ragendja.auth.models import User
from ragendja.dbutils import transaction
from ithink import taggable
import random

GENDERS = [0, 1]

class XnUser(User):
    uid = db.StringProperty(required=True)
    
    sex = db.IntegerProperty(choices=GENDERS)
    birth_year = db.StringProperty()
    birth_month = db.StringProperty()
    birth_day = db.StringProperty()
    home_country = db.StringProperty()
    home_province = db.StringProperty()
    home_city = db.StringProperty()
    pic_url = db.LinkProperty() #head_url
    
    friends_uids = db.StringListProperty()
    friends_keys = db.ListProperty(db.Key)
    friends_thoughts = db.ListProperty(db.Key)
    
    voted_thoughts = db.ListProperty(db.Key)
    num_votes = db.IntegerProperty(default=0)
    num_agrees = db.IntegerProperty(default=0)
    num_disagrees = db.IntegerProperty(default=0)
    my_thoughts = db.ListProperty(db.Key)
    num_thoughts = db.IntegerProperty(default=0)
    comments = db.ListProperty(db.Key)
    num_comments = db.IntegerProperty(default=0)
    recommended_thoughts = db.ListProperty(db.Key) #opinions friends invites you to
    
    followers = db.ListProperty(db.Key)
    num_followers = db.IntegerProperty(default=0)
    followings = db.ListProperty(db.Key)
    
    def __unicode__(self): 
        return u"%s" % self.username
    
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
    
    @transaction
    def voted_agree(self, thought):
        self.num_agrees += 1
        self.num_votes += 1
        self.voted_thoughts.append(thought.key())
        self.put()
    
    @transaction
    def voted_disagree(self, thought):
        self.num_disagrees += 1
        self.num_votes += 1
        self.voted_thoughts.append(thought.key())
        self.put()
        
    @transaction
    def add_comment(self, comment):
        self.comments.append(comment.key())
        self.num_comments += 1
        self.put()
        
    @transaction
    def add_thought(self, thought):
        self.my_thoughts.append(thought.key())
        self.num_thoughts += 1
        self.put()
        
    @transaction
    def add_friend_thought(self, thought):
        self.friends_thoughts.append(thought.key())
        self.put()
        
    @transaction
    def add_recommended(self, thought):
        self.recommended_thoughts.append(thought.key())
        self.put()
        
    @transaction
    def add_follower(self, follower):
        if follower.key() not in self.followers:
            self.followers.append(follower.key())
            self.num_followers += 1
            self.put()
    
    @transaction
    def add_following(self, user):
        if user.key() not in self.followings:
            self.followings.append(user.key())
            self.put()
    
class Thought(db.Model, taggable.Taggable):
    owner = db.ReferenceProperty(XnUser)
    content = db.StringProperty(required=True)
    note = db.StringProperty()
    agreed_users = db.ListProperty(db.Key)
    disagreed_users = db.ListProperty(db.Key)
    num_votes = db.IntegerProperty(default=0)
    date_created = db.DateTimeProperty(auto_now_add=True)
    comments = db.ListProperty(db.Key) #only direct comments
    num_total_comments = db.IntegerProperty(default=0) #number of all comments including replies
    followers = db.ListProperty(db.Key)
    
    def __init__(self, parent=None, key_name=None, app=None, **entity_values):
                    db.Model.__init__(self, parent, key_name, app, **entity_values)
                    taggable.Taggable.__init__(self)
    
    def __unicode__(self):
        return u'%s' % self.content
    
    @transaction
    def vote_agree(self, voter):
        self.num_votes += 1
        self.agreed_users.append(voter.key())
        self.put()
    
    @transaction
    def vote_disagree(self, voter):
        self.num_votes += 1
        self.disagreed_users.append(voter.key())
        self.put()
        
    @transaction
    def add_comment(self, comment):
        if not comment.reply_to:
            self.comments.append(comment.key())
        self.num_total_comments += 1
        self.put()
        
    @transaction
    def add_follower(self, follower):
        if follower.key() not in self.followers:
            self.followers.append(follower.key())
            self.put()

class Feature(db.Model):
    thought = db.ReferenceProperty(Thought)
    date_created = db.DateTimeProperty(auto_now_add=True)
    
class Comment(db.Model):
    author = db.ReferenceProperty(XnUser)
    thought = db.ReferenceProperty(Thought)
    content = db.TextProperty(required=True)
    reply_to = db.SelfReferenceProperty(collection_name='replies')
    replies_list = db.ListProperty(db.Key)
    date_created = db.DateTimeProperty(auto_now_add=True)
    
    def get_formated_date(self):
        return self.date_created.strftime('%Y-%m-%dT%H:%M:%SZ')
    
    @transaction
    def add_reply(self, reply):
        self.replies_list.append(reply.key())
        self.put()
        
class Note(db.Model):
    from_user = db.ReferenceProperty(XnUser, collection_name='written_notes')
    to_user = db.ReferenceProperty(XnUser, collection_name='received_notes')
    content = db.TextProperty(required=True)
    is_read = db.BooleanProperty(default=False)
    date_created = db.DateTimeProperty(auto_now_add=True)
    
class SessionInfo(db.Model):
    session_key = db.StringProperty(required=True)
    uid = db.StringProperty(required=True)
    date_created = db.DateTimeProperty(auto_now_add=True)
    last_used = db.DateTimeProperty()
    
    def __unicode__(self):
        return u'uid:%s session_key:%s' % (self.uid, self.session_key)
    
    @staticmethod
    def get_avail_session():
        return SessionInfo.all().order('-date_created').get()

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