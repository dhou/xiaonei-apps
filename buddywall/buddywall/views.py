from django.views.generic.simple import direct_to_template
from django.http import HttpResponse
from google.appengine.api.datastore_errors import BadValueError
from pyxn import XiaoneiError
from google.appengine.api.urlfetch_errors import DownloadError
from urlparse import urljoin
from google.appengine.runtime import apiproxy_errors
from django.core.urlresolvers import reverse
from buddywall.models import change_count, get_count
from buddywall.utils import reverse_xn
import sys
import logging
import pyxn.djangoxn as xn
from django.template import Context, loader
from django.utils import simplejson
from django.conf import settings
import random
from models import XnUser
from django.http import HttpResponseServerError
from google.appengine.api import memcache

SECS_DAY = 3600*24
SECS_HOUR = 3600
SECS_HALFHOUR = 1800
SECS_MIN = 60
SP_IMGS = [settings.MEDIA_URL+'images/cartman.png',
           settings.MEDIA_URL+'images/kenny.png',
           settings.MEDIA_URL+'images/kyle.png',
           settings.MEDIA_URL+'images/stan.png']

COUNTER_MALES = 'counter_males'
COUNTER_FEMALES = 'counter_females'
COUNTER_YEAR_PRE = 'counter_year_'

    
BG_STYLES={
           0:'',
           }

for x in range(1,76):
    BG_STYLES[x] = settings.MEDIA_URL + ('images/patterns/patt_%s.jpg' % x)

def home(request):
    return HttpResponse('Hello!') 

def get_or_create_xnuser(xn):
    """Utility function
    Get XnUser if already exists,
    Otherwise, call xn api to get user info and create XnUser instance
    @param xn: An authenticated Xiaonei instance 
    """
    #use memcache to cache the user instance
    user = memcache.get(xn.uid)
    if not user:
        user = XnUser.get_by_key_name('uid:'+xn.uid)
        if user is None:
            logging.debug('no user found in db, getting userinfo again')
            try:
                user_info = xn.users.getInfo(uids=[xn.uid], fields=['name'])[0]
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
                
            try:
                user, created = XnUser.get_or_insert_by_uid(xn.uid, username=user_info['name'])
            except BadValueError, e:
                logging.error('Failed to save user data: %s' % e)
                raise
            except:
                logging.error("Unexpected error")
                raise
            else:
                logging.debug('got user[created: %s]: %s' % (created,user.username))
        else:
            logging.debug('user exists in db')
            try:
                if user.friends:
                    logging.debug('purge remaining friends data')
                    user.friends = None
            except:
                logging.debug('no remaining friends data')
        memcache.set(xn.uid, user, SECS_DAY)
        logging.debug('user added to memcache')
    else:
        logging.debug('memcache hit for user %s' % user.username)
    return user

def get_selected_uids(user):
    return user.selected_uids
    
def get_iframe_url():
    return urljoin(settings.SERVER_URL, reverse('get_user_info'))

@xn.require_add()
def canvas(request):
    logging.debug('appname is %s' % settings.XIAONEI_APP_NAME)
    logging.debug('got post: %s' % request.POST)
    xn = request.xiaonei
    
    user = get_or_create_xnuser(xn)
    
    friends = friends_get(xn)
# xiaonei doesn't give you more than 500 friends
    selected_uids = get_selected_uids(user)
    wall_name = user.wall_name
    uids = []
    if selected_uids:
        for f in friends:
            if f in selected_uids:
                uids.append({'uid':f, 'selected':True})
            else:
                uids.append({'uid':f, 'selected':False})
    else:
        uids = [{'uid':uid, 'selected':True} for uid in friends]
    
    if user.bg_style:
        bg_patt_url = get_bg_style(user.bg_style)
    else:
        bg_patt_url = ''
    return direct_to_template(request, 'canvas.xnml',
                              extra_context={'uids':uids,
                                             'uid': xn.uid,
                                             'username': user.username,
                                             'wall_name':wall_name,
                                             'current':'home',
                                             'iframe_src':get_iframe_url(),
                                             'bg_url':bg_patt_url},)
    
def get_bg_style(style_id):
    return BG_STYLES[style_id]
    
@xn.require_add()
def refresh_wall(request):
    xn = request.xiaonei
    post = request.POST
    selected = post.getlist('selected[]')
    logging.debug('got selected: %s' % selected)
    wall_name = post['wall-name']
    logging.debug('got wallname: %s' % wall_name)
    
    try:
        user = get_or_create_xnuser(xn)
        selected_old = get_selected_uids(user)
        logging.debug('got user, going to update selected friends')
        if post.has_key('selall'):
            logging.debug('select all friends')
            all_uids = post.getlist('alluids[]')
            user.selected_uids = all_uids
            selected = all_uids
        
        user.selected_uids = selected
        user.wall_name = wall_name
        user.put()
        memcache.set(xn.uid, user, SECS_DAY)
    except apiproxy_errors.OverQuotaError, message:
        # Record the error in your logs
        logging.error(message)
        # Display an informative message to the user
        logging.error('Storage quota exceeded! selected_uids and wall_name not saved')
    
    #shuffle it a bit!
    random.shuffle(selected)
    if user.bg_style:
        bg_patt_url = get_bg_style(user.bg_style)
    else:
        bg_patt_url = ''
    
    logging.debug('setting profile xnml')
    t = loader.get_template('profile.xnml')
    c = Context({'uids':selected,
                 'app_url':xn.get_app_url(),
                 'num_buddies':len(selected),
                 'wall_name':wall_name,
                 'username':user.username,
                 'media_url':settings.MEDIA_URL,
                 'bg_url':bg_patt_url,
                 })
    prof = t.render(c)
#    logging.debug('profile xnml: %s' % prof)
    try:
        rc = xn.profile.setXNML(profile=prof)
        logging.debug('setxnml response: %s ' % rc)
    except XiaoneiError, e:
        logging.error('failed to setxnml for %s' % user.username)
        logging.error(e)
        refresh_ok = False
    except:
        logging.error('Unknown error when calling setxnml for %s' % user.username)
        exception = sys.exc_info()[0]
        logging.exception(exception)
        refresh_ok = False
    else:
        refresh_ok = True
    
    #send notification to newly added people
    selected_delta = filter(lambda x: x not in selected_old, selected)
    
    logging.debug('notify? %s' % post.has_key('notify'))
    
    if selected_delta and post.has_key('notify'):
        logging.debug('Sending notification to newly added people')
        t = loader.get_template('notify_picadded.xnml')
        try:
            c = Context({'uid':xn.uid,
                         'app_url':xn.get_app_url(),
                         })
            msg = t.render(c)
            logging.debug('Sending notification to %s...' % selected_delta)
            rc = xn.notifications.send(to_ids=selected_delta[:20], notification=msg)
        except XiaoneiError, e:
            logging.error('Error sending notification')
            logging.error(e)
        except:
            logging.error("Unknown error when sending notification")
            exception = sys.exc_info()[0]
            logging.exception(exception)
        else:
            logging.debug('Notification sent successfully')
    else:
        logging.debug('not sending notifications because selected_delta[%s] and notify[%s]' % (selected_delta, post.has_key('notify')))

    #publish action for 1 out of 3 visits, to avoid too much timeout
    if random.choice([i==0 for i in range(3)]):
        if selected_delta:
            action_names = selected_delta[:3]
        else:
            action_names = selected[:3]
        buddy_names = xn.users.getInfo(uids=action_names, fields=['name'])
        buddy_names = [buddy['name'] for buddy in buddy_names]
        
        app_url = xn.get_app_url()
        logging.debug('app_url: %s' % app_url)    
        logging.debug('publishing action')
        try:
            resp = xn.feed.publishTemplatizedAction(template_id='1', title_data=simplejson.dumps({'app_url':app_url,}), body_data=simplejson.dumps({'buddys':','.join(buddy_names), 'actor_name':user.username, 'app_url':app_url}))
        except XiaoneiError, e:
            logging.error("Error when publishing action")
            logging.error(e)
        except:
            logging.error("Unknown Error when publishing action")
            exception = sys.exc_info()[0]
            logging.exception(exception)
        else:
            logging.debug('action published')
    return direct_to_template(request, 'refreshed.xnml',
                              extra_context={'uid':xn.uid,
                                             'refresh_ok':refresh_ok,
                                             },)
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
            memcache.set('friends_'+xn.uid, friends, SECS_HALFHOUR)
            logging.debug('added friends to memcache for %s' % xn.uid)
    else:
        logging.debug('hit memcache friends.get for %s' % xn.uid)
    return friends

def refresh_user_cache(user):
    memcache.set(user.uid, get_user_from_db(user.uid), SECS_DAY)
    
def get_user_from_db(uid):
    return XnUser.get_by_key_name('uid:'+uid)

@xn.require_add()
def who_has_me(request):
    xn = request.xiaonei
    user = get_or_create_xnuser(xn)
    ppl = memcache.get('appusers_'+xn.uid)
    if not ppl:
        try:
#            ppl = xn.friends.getAppUsers()
            ppl = xn.friends.getAppFriends()
        except XiaoneiError,e:
            logging.error('Error calling friends.getappusers')
            logging.error(e)
            raise
        except DownloadError,e:
            logging.error('DownloadError caught while calling getappusers')
            logging.error(e)
            raise
        except:
            logging.error('Unknown error while calling friends.getappusers')
            exception = sys.exc_info()[0]
            logging.exception(exception)
            raise
        else:
            memcache.set('appusers_'+xn.uid, ppl, SECS_DAY)
            logging.debug('added appusers to memcache for %s' % xn.uid)
            user.app_users = ppl
            user.put()
            refresh_user_cache(user)
    else:
        logging.debug('hit memcache appusers for %s' % xn.uid)
    logging.debug('got appusers[%s]: %s' % (len(ppl),ppl))
    if not user.app_users and ppl:
        user.app_users = ppl
        user.put()
        refresh_user_cache(user)
    
    friends = friends_get(xn)
            
    diff = filter(lambda x:x not in ppl, friends)
    logging.debug('friends without app installed: %s' % diff)
    return direct_to_template(request, 'whohasme.xnml',
                              extra_context={'uids':ppl,
                                             'diff': diff,
                                             'current':'whohasme',
                                             },)

@xn.require_add()
def notify(request):
    xn = request.xiaonei
    post = request.POST
    if post.has_key('uids[]'):
        uids = post.getlist('uids[]')
        logging.debug('got uids: %s' % uids)
    #send notifications
        t = loader.get_template('notify_invite.xnml')
        try:
            c = Context({'uid':xn.uid,
                         'app_url':xn.get_app_url(),
                         })
            msg = t.render(c)
            logging.debug('Sending notification to %s...' % uids)
            rc = xn.notifications.send(to_ids=uids[:30], notification=msg)
        except XiaoneiError, e:
            logging.error('Error sending notification')
            logging.error(e)
        except:
            logging.error("Unknown error when sending notification")
            exception = sys.exc_info()[0]
            logging.exception(exception)
        else:
            logging.debug('Notification sent successfully')
            
        return direct_to_template(request, 'notified.xnml',
                              extra_context={'uid':xn.uid,
                                             },)
        
def get_num_avail(user):
    """
    Get the number of background patterns available to a user
    One more pattern every 5 people invited
    """
    num = user.num_invited if user.num_invited else 0
    return 1 + (num/5)*2

@xn.require_add()
def choose_bg(request):
    xn = request.xiaonei
    post = request.POST
    logging.debug('got post: %s' % post)
    user = get_or_create_xnuser(xn)
    current_bg = user.bg_style
    num_avail = get_num_avail(user) #number of bg styles available to user, one for free
    return direct_to_template(request, 'choosebg.xnml',
                              extra_context={'uid':xn.uid,
                                             'exclude_ids':','.join(user.app_users) if user.app_users else '',
                                             'current_bg':current_bg,
                                             'bg_styles':BG_STYLES,
                                             'user':user,
                                             'num_avail':num_avail,
                                             'current':'choosebg',
                                             'total_bgs':len(BG_STYLES)-1,
                                             'iframe_src':get_iframe_url(),
                                             },)
    
@xn.require_add()
def invite(request):
    post = request.POST
    logging.debug('got post: %s' % post)
    xn = request.xiaonei
    user = get_or_create_xnuser(xn)
    next = reverse('post_invite')
    next = next[len(settings.XIAONEI_CALLBACK_PATH):]
    return direct_to_template(request, 'invite.xnml',
                          extra_context={
                                         'exclude_ids':','.join(user.app_users) if user.app_users else '',
                                         'next':next,
                                         'current':'invite',
                                         },)

@xn.require_add()
def post_invite(request):
    post = request.POST
    logging.debug('got post: %s' % post)
    xn = request.xiaonei
    user = get_or_create_xnuser(xn)
    invited = post.getlist('ids[]')
    if not user.num_invited:
        user.num_invited = len(invited)
    else:
        user.num_invited += len(invited)
    user.put()
    refresh_user_cache(user)
    url = reverse_xn('choose_bg', xn.get_app_url())
    return xn.redirect(url)

@xn.require_add()
def set_bg(request):
    post = request.POST
    logging.debug('got post: %s' % post)
    xn = request.xiaonei
    user = get_or_create_xnuser(xn)
    selected_bg = post.get('selected[]')
    user.bg_style = int(selected_bg)
    if not user.app_users:
        user.app_users = []
    user.put()
    logging.debug('set bg_style: %s' % selected_bg)
    refresh_user_cache(user)
    return xn.redirect(reverse_xn('canvas', xn.get_app_url()))
    
def get_user_info(request):
    logging.debug('iframe got get: %s' % request.GET)
    logging.debug('appname is %s' % settings.XIAONEI_APP_NAME)
    xn = request.xiaonei
    xn.check_session(request)
    user = XnUser.get_by_key_name('uid:'+xn.uid)
    if not user.sex:
        logging.debug('no extra user info yet. trying to get now')
        try:
            user_info = xn.users.getInfo(uids=[xn.uid], fields=['name','sex','headurl','birthday','hometown_location'])[0]
            logging.debug('got userinfo: %s' % user_info)
        except XiaoneiError, e:
            logging.error('Failed calling users.getinfo')
            logging.error(e)
            return HttpResponse('error with users.getinfo', mimetype='text/html')
        except:
            logging.error('Unknown error while calling users.getinfo')
            exception = sys.exc_info()[0]
            logging.exception(exception)
            return HttpResponse('error with users.getinfo', mimetype='text/html')
        else:
            birthday = user_info['birthday']
            if birthday:
                year, month, day = birthday.split('-')
                logging.debug('got year: %s, month: %s, day: %s' % (year, month, day))
            
            user.sex=int(user_info['sex'])
            user.head_url=user_info['headurl']
            user.birth_year = year
            user.birth_month = month
            user.birth_day = day
            user.home_country=user_info['hometown_location'].get('country','')
            user.home_province=user_info['hometown_location'].get('province','')
            user.home_city=user_info['hometown_location'].get('city','')
            user.put()
            #inc user counters
            if user.sex == 1:
                logging.debug('+1 for males')
                change_count(COUNTER_MALES,1)
            else:
                logging.debug('+1 for females')
                change_count(COUNTER_FEMALES,1)
            #inc age counters
            logging.debug('+1 for birth year %s' % user.birth_year)
            change_count(COUNTER_YEAR_PRE+user.birth_year,1)
    else:
        logging.debug('already has extra user info')
        
    logging.debug('getting app users')
    try:
        ppl = xn.friends.getAppUsers()
    except XiaoneiError,e:
        logging.error('Error calling friends.getappusers')
        logging.error(e)
        return HttpResponse('error with users.getAppUsers', mimetype='text/html')
    except DownloadError,e:
        logging.error('DownloadError caught while calling getappusers')
        logging.error(e)
        return HttpResponse('error with users.getAppUsers', mimetype='text/html')
    except:
        logging.error('Unknown error while calling friends.getappusers')
        exception = sys.exc_info()[0]
        logging.exception(exception)
        return HttpResponse('error with users.getAppUsers', mimetype='text/html')
    else:
        logging.debug('got appusers: %s' % ppl)
        memcache.set('appusers_'+xn.uid, ppl, SECS_DAY)
        user.app_users = ppl
        user.put()
        refresh_user_cache(user)
        logging.debug(u'added appusers to user: %s' % user.username)
    
    return HttpResponse('ok', mimetype='text/html')

def stats(request):
    males = get_count(COUNTER_MALES)
    females = get_count(COUNTER_FEMALES)
    return HttpResponse('males: %s females: %s' % (males, females), mimetype='text/html')
        
def error_500(request):
    """ Custom exception handler for Django.
    
    Note that settings.DEBUG must be False or
    this handler is never run.
    """
    
    # Get the latest exception from Python system service
    exception = sys.exc_info()[0]
    
    logging.error("Uncaught exception got through, rendering 500 page")
    logging.error("Exception is DownloadError? %s" % isinstance(exception, DownloadError)) 
    logging.exception(exception)
    
    spurl = random.choice(SP_IMGS)
    return direct_to_template(request, '500.html',
                              extra_context={'img':spurl,})