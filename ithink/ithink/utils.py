from django.core.urlresolvers import reverse
from google.appengine.api import memcache
from google.appengine.api.urlfetch_errors import DownloadError
from models import change_count, XnUser
from google.appengine.api.datastore_errors import BadValueError
from taggable import Tag
from ithink.models import SessionInfo
from django.utils import simplejson
import re
import time
import sys
import random
import logging
import datetime
import settings
from pyxn import Xiaonei, XiaoneiError

COUNTER_MALES = 'counter_males'
COUNTER_FEMALES = 'counter_females'
COUNTER_YEAR_PRE = 'counter_year_'
COUNTER_THOUGHTS = 'counter_thoughts'

SECS_DAY = 3600*24
SECS_HOUR = 3600
SECS_HALFHOUR = 1800
SECS_MIN = 60
SECS_5MIN = 300

def reverse_xn(viewname, app_url, urlconf=None, args=None, kwargs=None):
    """
    Returns the reversed url for the app
    """
    return app_url + reverse(viewname, urlconf, args, kwargs).replace(getattr(settings, "XIAONEI_CALLBACK_PATH", ""), '')

def create_xn_instance(session_key, uid):
    xn = Xiaonei(settings.XIAONEI_API_KEY,
                                settings.XIAONEI_SECRET_KEY,
                                app_name=getattr(settings, 'XIAONEI_APP_NAME', None),
                                callback_path=getattr(settings, 'XIAONEI_CALLBACK_PATH', None),
                                internal=getattr(settings, 'XIAONEI_INTERNAL', True),
                                proxy=None)
    xn.session_key = session_key
    xn.uid = uid
    return xn

def get_percent(value, divider):
    return int(round(float(value)/divider*100,0))

def abbr(value,len):
    if len(value) > len:
        return value[:len-3]+u'...'
    else:
        return value
    
def prof(fn):
    def wrapper(*args, **kwargs):
        entry = datetime.datetime.now()
        result = fn(*args, **kwargs)
        exit = datetime.datetime.now()
        logging.info('runtime: %s' % (exit-entry))
        return result
    return wrapper
    
def refresh_user_cache(user):
    memcache.set(user.uid, get_user_by_uid(user.uid), SECS_DAY)
    
def get_user_by_uid(uid):
    return XnUser.get_by_key_name('uid:'+uid)

def get_or_create_xnuser(xn):
    """Utility function
    Get XnUser if already exists,
    Otherwise, call xn api to get user info and create XnUser instance
    @param xn: An authenticated Xiaonei instance 
    """
#    memcache.flush_all()
    #use memcache to cache the user instance
    user = memcache.get(xn.uid)
    if not user:
        user = XnUser.get_by_key_name('uid:'+xn.uid)
        if user is None:
            logging.debug('no user found in db, getting userinfo again')
            try:
                user_info = xn.users.getInfo(uids=[xn.uid], fields=['name','sex','headurl','birthday','hometown_location'])[0]
                logging.debug('got userinfo: %s' % user_info)
            except XiaoneiError, e:
                logging.error('Failed calling users.getinfo')
                logging.error(e)
                raise
            except:
                logging.error('Unknown error while calling users.getinfo')
                exception = sys.exc_info()[0]
                logging.exception(exception)
                raise
            else:
                birthday = user_info['birthday']
                if birthday:
                    year, month, day = birthday.split('-')
                    logging.debug('got year: %s, month: %s, day: %s' % (year, month, day))
            try:
                user, created = XnUser.get_or_insert_by_uid(xn.uid, 
                                                            username=user_info['name'], 
                                                            sex=int(user_info['sex']),
                                                            pic_url=user_info['headurl'], 
                                                            birth_year=year,
                                                            birth_month=month,
                                                            birth_day=day,
                                                            home_country=user_info['hometown_location'].get('country',''),
                                                            home_province=user_info['hometown_location'].get('province',''),
                                                            home_city=user_info['hometown_location'].get('city',''))
            except BadValueError, e:
                logging.error('Failed to save user data: %s' % e)
                raise
            except:
                logging.error("Unexpected error while creating user")
                exception = sys.exc_info()[0]
                logging.exception(exception)
                raise
            else:
                logging.debug('got user[created: %s]: %s' % (created,user.username))
                friends = friends_get(xn)
                logging.debug('got friends: %s' % friends)
                user.friends_uids = friends if friends else []
                user.put()
                #inc user counters
                if user.sex == 1:
                    change_count(COUNTER_MALES,1)
                else:
                    change_count(COUNTER_FEMALES,1)
                #inc age counters
                logging.debug('+1 for birth year %s' % user.birth_year)
                change_count(COUNTER_YEAR_PRE+user.birth_year,1)
        else:
            logging.debug(u'got user: %s' % user)
            if not user.friends_uids:
                logging.debug('no friends found, getting friends again')
                friends = friends_get(xn)
                logging.debug('got friends: %s' % friends)
                user.friends_uids = friends if friends else []
                user.put()
        memcache.set(xn.uid, user, SECS_DAY)
        logging.debug('user added to memcache')
    else:
        logging.debug(u'memcache hit for user %s' % user.username)
        if not user.friends_uids:
            logging.debug('no friends found, getting friends again')
            friends = friends_get(xn)
            logging.debug('got friends: %s' % friends)
            user.friends_uids = friends if friends else []
            user.put()
            memcache.set(xn.uid, user, SECS_DAY)
            logging.debug('user updated to memcache')
    return user

def friends_get(xn):
    """Memcached enabled friends.get
    """
    friends = memcache.get('friends_'+xn.uid)
    if not friends:
        try:
            friends = xn.friends.get()
        except XiaoneiError,e:
            logging.error('Error calling friends.get')
            logging.error(e)
            raise
        except DownloadError,e:
            logging.error('DownloadError caught while calling friends.get')
            logging.error(e)
            raise
        except:
            logging.error('Unknown error while calling friends.get')
            exception = sys.exc_info()[0]
            logging.exception(exception)
            raise
        else:
            logging.debug('got friends: %s' % friends)
            memcache.set('friends_'+xn.uid, friends, SECS_HOUR)
            logging.debug('added friends to memcache for %s' % xn.uid)
    else:
        logging.debug('hit memcache friends.get for %s' % xn.uid)
    return friends

def gen_tag_cloud():
    tags = memcache.get('tag_cloud')
    if not tags:
        tags = Tag.get_cloud(steps=5, limit=50)
        for tag in tags:
            logging.debug('got tags: %s[%s]' % (tag.tag, tag.font_size))
            tag.font_size_percent = 80 + int(tag.font_size)*20
        random.shuffle(tags)
        memcache.set('tag_cloud', tags, SECS_HOUR)
        
def pub_feed(xn, template_id, title_data, body_data):
    #publish feed
    logging.debug('publishing feed')
    try:
        resp = xn.feed.publishTemplatizedAction(template_id=template_id, 
                                                title_data=simplejson.dumps(title_data), 
                                                body_data=simplejson.dumps(body_data))
    except XiaoneiError,e:
        logging.error('Failed to call feed.publishTemplatizedAction')
        logging.error(e)
    except:
        logging.error("Unknown error when publishing feed for new story piece")
        exception = sys.exc_info()[0]
        logging.exception(exception)
    else:
        logging.debug('feed published with response: %s' % resp)
        
def send_notification(xn, ids, msg):
    try:
        rc = xn.notifications.send(to_ids=ids, notification=msg)
    except XiaoneiError,e:
        logging.error('Failed to call notifications.send')
        logging.error(e)
        if e.code == '10600':
            logging.debug('notification limit reached, trying to use other session key')
            session = SessionInfo.get_avail_session()
            if session:
                logging.debug(u'got available session: %s' % session)
                xn = create_xn_instance(session_key=session.session_key, uid=session.uid)
                try:
                    rc = xn.notifications.send(to_ids=ids, notification=msg)
                except XiaoneiError,e:
                    logging.error('Failed to call notifications.send with other session')
                    logging.error(e)
                    if e.code == '10600':
                        logging.debug('this session has expired too. removing from db...')
                        session.delete()
                except:
                    logging.error("Unknown Error when sending notification with other session")
                    exception = sys.exc_info()[0]
                    logging.exception(exception)
            else:
                logging.debug('no available session. abort notification')
    except:
        logging.error("Unknown Error when sending notification")
        exception = sys.exc_info()[0]
        logging.exception(exception)
    else:
        logging.debug("Notification success with response: %s" % rc)
        
def timeparse(t, format):
    """Parse a time string that might contain fractions of a second.
    
    Fractional seconds are supported using a fragile, miserable hack.
    Given a time string like '02:03:04.234234' and a format string of
    '%H:%M:%S', time.strptime() will raise a ValueError with this
    message: 'unconverted data remains: .234234'.  If %S is in the
    format string and the ValueError matches as above, a datetime
    object will be created from the part that matches and the
    microseconds in the time string.
    """
    logging.debug('parsing datetime...')
    try:
        return datetime.datetime(*time.strptime(t, format)[0:6]).time()
    except ValueError, msg:
        if "%S" in format:
            msg = str(msg)
            mat = re.match(r"unconverted data remains:"
                           " \.([0-9]{1,6})$", msg)
            if mat is not None:
                # fractional seconds are present - this is the style
                # used by datetime's isoformat() method
                frac = "." + mat.group(1)
                t = t[:-len(frac)]
                t = datetime.datetime(*time.strptime(t, format)[0:6])
                microsecond = int(float(frac)*1e6)
                return t.replace(microsecond=microsecond)
            else:
                mat = re.match(r"unconverted data remains:"
                               " \,([0-9]{3,3})$", msg)
                if mat is not None:
                    # fractional seconds are present - this is the style
                    # used by the logging module
                    frac = "." + mat.group(1)
                    t = t[:-len(frac)]
                    t = datetime.datetime(*time.strptime(t, format)[0:6])
                    microsecond = int(float(frac)*1e6)
                    return t.replace(microsecond=microsecond)
        raise

def add_thought_meta(t,user):
    t.date_created_str = t.date_created.strftime('%Y-%m-%dT%H:%M:%SZ')
    t.percent_agreed = get_percent(len(t.agreed_users), t.num_votes)
    if t.agreed_users and user.key() in t.agreed_users:
        t.agreed = True
        t.voted = True
    elif t.disagreed_users and user.key() in t.disagreed_users:
        t.agreed = False
        t.voted = True
    else:
        t.agreed = False
        t.voted = False