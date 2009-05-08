# Create your views here.
from django.conf import settings
from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseServerError, \
    HttpResponseForbidden, HttpResponseNotFound, HttpResponseBadRequest
from django.template import Context, loader
from django.utils import simplejson
from django.views.generic.simple import direct_to_template
from google.appengine.api import memcache
from google.appengine.api.datastore_errors import BadValueError
from google.appengine.api.urlfetch_errors import DownloadError
from google.appengine.ext import db
from google.appengine.runtime import apiproxy_errors
from ragendja.dbutils import transaction
from models import XnUser, Thought, change_count, Comment
from utils import create_xn_instance, reverse_xn, get_percent, prof
from urlparse import urljoin
from taggable import Tag
from ithink.models import Note, get_count, SessionInfo, Feature
from ithink.utils import get_or_create_xnuser, refresh_user_cache,\
    get_user_by_uid, send_notification, pub_feed, COUNTER_THOUGHTS,\
    add_thought_meta
import datetime
import logging
import pyxn.djangoxn as xn
import random
import re
import sys
import time

SECS_DAY = 3600*24
SECS_HOUR = 3600
SECS_HALFHOUR = 1800
SECS_MIN = 60
SECS_5MIN = 300

COMMENTS_PAGELEN = 10
THOUGHTS_PAGELEN = 10
PEOPLE_PAGELEN = 10
STUFF_PAGELEN = 8
VOTERS_PAGELEN = 10

SP_IMGS = [settings.MEDIA_URL+'images/cartman_130.jpg',
           settings.MEDIA_URL+'images/kenny_130.jpg',
           settings.MEDIA_URL+'images/kyle_130.jpg',
           settings.MEDIA_URL+'images/stan_130.jpg']

#s3_conn = S3.AWSAuthConnection(settings.AWS_KEY,settings.AWS_SECRET)

def postadd(request):
    logging.debug('postadd called with data: %s' % request.POST)
#    memcache.flush_all()
    xn = request.xiaonei
    xn.check_session(request)
    user = get_or_create_xnuser(xn)
    
    #scan for existing friends stories and pieces
    friends = XnUser.all().filter('friends_uids = ', user.uid).fetch(500)
    for f in friends:
        logging.debug(u'i have a friend here: %s' % f)
        keys = f.my_thoughts
        if keys:
            logging.debug('adding friend thoughts to my list')
            if keys[0] not in user.friends_thoughts:
                user.friends_thoughts.extend(keys)
        if user.key() not in f.friends_keys:
            logging.debug(u'added %s to %s friends_keys list' % (user, f))
            f.friends_keys.append(user.key())
            f.put()
        user.friends_keys.append(f.key())
    user.put()
    refresh_user_cache(user)
    url = reverse_xn('home', xn.get_app_url())
    return xn.redirect(url)

@xn.require_add()
def home_canvas(request, sort='latest', offset=0):
    logging.debug('appname is %s' % settings.XIAONEI_APP_NAME)
    logging.debug('devmode: %s' % settings.DEVELOPMENT_MODE)
    logging.debug('got post: %s' % request.POST)
    xn = request.xiaonei
    user = get_or_create_xnuser(xn)
#    user = get_user_by_uid(xn.uid)
#    refresh_user_cache(user)
    logging.debug(u'got user: %s' % user.username)
#    tags = gen_tag_cloud()
    tags = Tag.get_cloud(steps=5, limit=40)
    for tag in tags:
#        logging.debug(u'font size for %s: %s' % (tag,tag.font_size))
        if tag.font_size:
            tag.font_size_percent = 80 + int(tag.font_size)*20
        else:
            tag.font_size_percent = 80
    random.shuffle(tags)
    
    if not offset:
        iframe_src = urljoin(settings.SERVER_URL, reverse('home_iframe_sorted_def', args=[sort]))
    else:
        iframe_src = urljoin(settings.SERVER_URL, reverse('home_iframe_sorted', args=[sort,offset]))
        
    session_iframe = urljoin(settings.SERVER_URL, reverse('get_session'))
    feature = Feature.all().order('-date_created').get()
    feature_url = urljoin(settings.SERVER_URL, reverse('feature'))
    return direct_to_template(request, 'home_canvas.xnml',
                              extra_context={'current':'home',
                                             'sort':sort,
                                             'uid':user.uid,
                                             'username':user.username,
                                             'iframe_src':iframe_src,
                                             'tags':tags,
                                             'num_thoughts':get_count(COUNTER_THOUGHTS),
                                             'session_iframe':session_iframe,
                                             'feature':feature,
                                             'feature_url':feature_url,
                                             },)
    
def feature_iframe(request):
    logging.debug('iframe got get: %s' % request.GET)
    xn = request.xiaonei
    xn.check_session(request)
    user = get_or_create_xnuser(xn)
    logging.debug(u'got user: %s' % user.username)
    feature = Feature.all().order('-date_created').get()
    thought = feature.thought
    add_thought_meta(thought, user)
    date_created = thought.date_created.strftime('%Y-%m-%dT%H:%M:%SZ')
    return direct_to_template(request, 'recommend_iframe.html',
                          extra_context={
                                         'uid':xn.uid,
                                         'session_key':xn.session_key,
                                         'thought':thought,
                                         'date_created':date_created,
                                         },)
    
    
def home_iframe(request, sort='votes', offset=0):
    logging.debug('iframe got get: %s' % request.GET)
    xn = request.xiaonei
    xn.check_session(request)
    user = get_or_create_xnuser(xn)
    logging.debug(u'got user: %s' % user.username)
    offset = int(offset)
    if sort == 'votes':
        thoughts = Thought.all().order('-num_votes').order('-date_created').fetch(THOUGHTS_PAGELEN+1, offset)
    elif sort == 'comments':
        thoughts = Thought.all().order('-num_total_comments').order('-date_created').fetch(THOUGHTS_PAGELEN+1, offset)
    elif sort == 'latest':
        thoughts = Thought.all().order('-date_created').fetch(THOUGHTS_PAGELEN+1, offset)
    elif sort == 'friends':
        keys = user.friends_thoughts
        if keys:
            thoughts = db.get(keys)
            thoughts.sort(key=lambda x:x.date_created, reverse=True)
            thoughts = thoughts[offset:offset+THOUGHTS_PAGELEN+1]
        else:
            thoughts = []
    has_next = len(thoughts) > THOUGHTS_PAGELEN
    # throw away the extra thought
    thoughts = thoughts[:THOUGHTS_PAGELEN]
    has_prev = offset > 0
    
    for t in thoughts:
        add_thought_meta(t, user)
            
    return direct_to_template(request, 'home_iframe.html',
                              extra_context={
                                             'uid':xn.uid,
                                             'session_key':xn.session_key,
                                             'thoughts':thoughts,
                                             'offset':offset+THOUGHTS_PAGELEN,
                                             'prev_offset':offset-THOUGHTS_PAGELEN,
                                             'has_next':has_next,
                                             'has_prev':has_prev,
                                             'page_len':THOUGHTS_PAGELEN,
                                             'sort':sort
                                             },)
    
@xn.require_add()
def new_canvas(request):
    logging.debug('got post: %s' % request.POST)
    xn = request.xiaonei
    user = get_or_create_xnuser(xn)
    iframe_src = urljoin(settings.SERVER_URL, reverse('new_iframe'))
    return direct_to_template(request, 'new_canvas.xnml',
                          extra_context={'current':'new',
                                         'uid':user.uid,
                                         'username':user.username,
                                         'iframe_src':iframe_src,
                                         },)
    
def new_iframe(request):
    logging.debug('iframe got get: %s' % request.GET)
    xn = request.xiaonei
    xn.check_session(request)
    user = get_or_create_xnuser(xn)
    logging.debug(u'got user: %s' % user.username)
    return direct_to_template(request, 'new_iframe.html',
                              extra_context={
                                             'uid':xn.uid,
                                             'session_key':xn.session_key,
                                             'user_pic':user.pic_url,
                                             'username':user.username
                                             },)


def create_thought(request):
    if request.method == 'POST':
        post = request.POST
        logging.debug('got post: %s' % post)
        
        uid = post['uid']
        user = XnUser.get_by_key_name('uid:'+uid)
        logging.debug(u'got user: %s' % user)
        
        session_key = post['session_key']
        xn = create_xn_instance(session_key, uid)
        
        thought = post['thought']
        tags = post['tags']
        note = post['note']
        logging.debug('got tags: %s' % tags)
        thought = Thought(owner=user, content=thought, note=note)
        thought.agreed_users.append(user.key())
        thought.num_votes = 1
        thought.put()
        logging.debug('created thought: %s' % thought.content)
        #inc global thought counter
        change_count(COUNTER_THOUGHTS, 1)
        if tags:
            logging.debug('setting tags: %s' % tags)
            thought.set_tags_from_string(tags)
        user.add_thought(thought)
        refresh_user_cache(user)
        friends = XnUser.all().filter('friends_uids =', uid).fetch(500)
        logging.debug('got existing friends: %s' % friends)
        if friends:
            for f in friends:
                f.add_friend_thought(thought)
        
        #publish feed
        title_data = {
                     'thought_url':reverse_xn('thought_detail', xn.get_app_url(), args=[thought.key().id()]),
                     'thought':thought.content,
                     }
        body_data = {'thought_url':reverse_xn('thought_detail', xn.get_app_url(), args=[thought.key().id()]),
                    'username':user.username,
                    }
        pub_feed(xn, '1', title_data, body_data)
            
        #send notifications to friends
        if post.has_key('notify'):
            t = loader.get_template('notify_new_thought.xnml')
            c = Context({'uid':xn.uid,
                         'sex':user.sex,
                         'thought_url':reverse_xn('thought_detail', xn.get_app_url(), args=[thought.key().id()]),
                         'thought':thought.content,
                         'profile_url':reverse_xn('profile_def', xn.get_app_url(), args=[uid]),
                         })
            msg = t.render(c)
            logging.debug('Sending notification to friends for new piece...')
            uids = user.friends_uids
            random.shuffle(uids)
            send_notification(xn, uids[:20], msg)
        
        url = reverse_xn('recommend',xn.get_app_url(),args=[thought.key().id()])
        return HttpResponse(simplejson.dumps({'url':url}), mimetype='application/json')
    else:
        return HttpResponseForbidden()

@xn.require_add()
def thought_detail(request, thought_id, cat='comments'):
    logging.debug('got post: %s' % request.POST)
    xn = request.xiaonei
    iframe_src = urljoin(settings.SERVER_URL, reverse('thought_iframe', kwargs={'cat':cat,'thought_id':thought_id}))
        
    return direct_to_template(request, 'thought_detail.xnml',
                          extra_context={'current':'thought',
                                         'iframe_src':iframe_src,
                                         'cat':cat,
                                         'thought_id':thought_id,
                                         },)
    
def thought_iframe(request, thought_id, cat='comments'):
    logging.debug('iframe got get: %s' % request.GET)
    xn = request.xiaonei
    xn.check_session(request)
    thought = Thought.get_by_id(int(thought_id))
    if not thought:
        return HttpResponseNotFound()
    logging.debug(u'got thought: %s' % thought)
    user = get_or_create_xnuser(xn)
    if thought.agreed_users and user.key() in thought.agreed_users:
        agreed = True
        voted = True
    elif thought.disagreed_users and user.key() in thought.disagreed_users:
        agreed = False
        voted = True
    else:
        voted = False
        agreed = False
    percent_agreed = get_percent(len(thought.agreed_users), thought.num_votes)
    date_created = thought.date_created.strftime('%Y-%m-%dT%H:%M:%SZ')
    
    if cat == 'comments':
        if thought.comments:
            comments_keys = thought.comments[::-1]
            if len(thought.comments) > COMMENTS_PAGELEN:
                has_next = True
                comments = db.get(comments_keys[:COMMENTS_PAGELEN])
            else:
                has_next = False
                comments = db.get(comments_keys)
            comments.sort(key=lambda x:x.date_created, reverse=True)
        else:
            comments = []
            has_next = False
        logging.debug('got comments: %s' % comments)
        for c in comments:
            if c.author.key() in thought.agreed_users:
                c.agreed = True
                c.voted = True
            elif c.author.key() in thought.disagreed_users:
                c.agreed = False
                c.voted = True
            else:
                c.voted = False
        return direct_to_template(request, 'thought_iframe_comments.html',
                              extra_context={
                                             'uid':xn.uid,
                                             'session_key':xn.session_key,
                                             'thought':thought,
                                             'voted':voted,
                                             'agreed':agreed,
                                             'percent_agreed':percent_agreed,
                                             'date_created':date_created,
                                             'comments':comments,
                                             'has_next':has_next,
                                             'offset':0,
                                             'page_len':COMMENTS_PAGELEN,
                                             },)
    elif cat == 'voters':
        agreed = thought.agreed_users[-1:-1-VOTERS_PAGELEN:-1]
        disagreed = thought.disagreed_users[-1:-1-VOTERS_PAGELEN:-1]
        agreed_voters = db.get(agreed) if agreed else []
        disagreed_voters = db.get(disagreed) if disagreed else []
        has_next_agrees = len(thought.agreed_users) > VOTERS_PAGELEN
        has_next_disagrees = len(thought.disagreed_users) > VOTERS_PAGELEN
        return direct_to_template(request, 'thought_iframe_voters.html',
                              extra_context={
                                             'uid':xn.uid,
                                             'session_key':xn.session_key,
                                             'thought':thought,
                                             'voted':voted,
                                             'agreed':agreed,
                                             'percent_agreed':percent_agreed,
                                             'date_created':date_created,
                                             'has_next_agrees':has_next_agrees,
                                             'has_next_disagrees':has_next_disagrees,
                                             'agreed_offset':0,
                                             'disagreed_offset':0,
                                             'agreed_voters':agreed_voters,
                                             'disagreed_voters':disagreed_voters,
                                             'page_len':VOTERS_PAGELEN,
                                             },)
    
@xn.require_add()
def tag_view(request, tag=None, sort='votes', offset=0):
    xn = request.xiaonei
    
    tags = Tag.get_cloud(steps=5, limit=50)
    for t in tags:
        logging.debug('got tags: %s[%s]' % (t.tag, t.font_size))
        t.font_size_percent = 80 + int(t.font_size)*20
    random.shuffle(tags)
    
    if tag:
        if not offset:
            iframe_src = urljoin(settings.SERVER_URL, reverse('tag_iframe_sorted_def', kwargs={'tag':tag,'sort':sort}))
        else:
            iframe_src = urljoin(settings.SERVER_URL, reverse('tag_iframe_sorted', kwargs={'tag':tag,'sort':sort,'offset':offset}))
        return direct_to_template(request, 'tag_view.xnml',
                          extra_context={'current':'tags',
                                         'sort':sort,
                                         'uid':xn.uid,
                                         'tag':tag,
                                         'tags':tags,
                                         'iframe_src':iframe_src,
                                         },)
    else:
        return direct_to_template(request, 'tag_view.xnml',
                          extra_context={'current':'tags',
                                         'sort':sort,
                                         'uid':xn.uid,
                                         'tags':tags,
                                         },)
    
def tag_iframe(request, tag, sort='votes', offset=0):
    logging.debug('tag_iframe got get: %s' % request.GET)
    offset = int(offset)
    xn = request.xiaonei
    xn.check_session(request)
    tag = Tag.get_by_tag_value(tag)
    logging.debug(u'got tag: %s' % tag)
    user = get_or_create_xnuser(xn)
    if tag:
        keys = tag.tagged
        if keys:
            #TODO memcache this
            thoughts = db.get(keys)
            logging.debug('got thoughts: %s' % thoughts)
            if sort == 'votes':
                thoughts.sort(key=lambda x:x.num_votes, reverse=True)
            elif sort == 'comments':
                thoughts.sort(key=lambda x:x.num_total_comments, reverse=True)
            elif sort == 'latest':
                thoughts.sort(key=lambda x:x.date_created, reverse=True)
            elif sort == 'friends':
                friends_keys = user.friends_thoughts
                joint_keys = [k for k in keys if k in friends_keys ]
                if joint_keys:
                    thoughts = db.get(joint_keys)
                    thoughts.sort(key=lambda x:x.date_created, reverse=True)
                else:
                    thoughts = []
            if offset + THOUGHTS_PAGELEN < len(thoughts):
                has_next = True
            else:
                has_next = False
            has_prev = offset > 0
            thoughts = thoughts[offset:offset+THOUGHTS_PAGELEN]
            
            for t in thoughts:
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
        else:
            thoughts = []
        logging.debug('has_next: %s' % has_next)
        logging.debug('has_prev: %s' % has_prev)
        return direct_to_template(request, 'tag_iframe.html',
                              extra_context={
                                             'uid':xn.uid,
                                             'session_key':xn.session_key,
                                             'thoughts':thoughts,
                                             'offset':offset+THOUGHTS_PAGELEN,
                                             'prev_offset':offset-THOUGHTS_PAGELEN,
                                             'has_next':has_next,
                                             'has_prev':has_prev,
                                             'page_len':THOUGHTS_PAGELEN,
                                             'sort':sort,
                                             'tag':tag
                                             },)
    else:
        return HttpResponseNotFound()

@xn.require_add()
def my(request,stuff='thoughts',cat='created',offset=0):
    xn = request.xiaonei
    user = get_or_create_xnuser(xn)
    if stuff == 'thoughts':
        if offset:
            iframe_src = urljoin(settings.SERVER_URL, reverse('my_iframe_thoughts_cat_sorted', kwargs={'cat':cat,'offset':offset}))
        else:
            iframe_src = urljoin(settings.SERVER_URL, reverse('my_iframe_thoughts_def', kwargs={'cat':cat}))
    else:
        if offset:
            iframe_src = urljoin(settings.SERVER_URL, reverse('my_iframe_stuff_sorted', kwargs={'stuff':stuff,'offset':offset}))
        else:
            iframe_src = urljoin(settings.SERVER_URL, reverse('my_iframe_stuff_def', kwargs={'stuff':stuff}))
        
    return direct_to_template(request, 'my.xnml',
                          extra_context={'current':'my',
                                         'uid':xn.uid,
                                         'num_thoughts':len(user.my_thoughts),
                                         'num_comments':len(user.comments),
                                         'num_votes':len(user.voted_thoughts),
                                         'iframe_src':iframe_src,
                                         'stuff':stuff,
                                         'cat':cat,
                                         },)

def format_datetime(obj):
    obj.date_created_str = obj.date_created.strftime('%Y-%m-%dT%H:%M:%SZ')

def my_iframe_thoughts(request,cat='created',offset=0):
    logging.debug('my_iframe got get: %s' % request.GET)
    logging.debug('cat is: %s' % cat)
    offset = int(offset)
    xn = request.xiaonei
    xn.check_session(request)
    user = get_or_create_xnuser(xn)
    keys= []
    if cat == 'created':
        keys = user.my_thoughts
    elif cat == 'voted':
        keys = user.voted_thoughts
        logging.debug('voted keys: %s' % keys)
    elif cat == 'commented':
        keys = user.comments
    elif cat == 'received':
        keys = user.recommended_thoughts
        
    if not keys:
        has_next = False
    elif keys and offset+THOUGHTS_PAGELEN >= len(keys):
        has_next = False
    else:
        has_next = True
    has_prev = offset > 0
        
    if cat == 'commented':
        comment_keys = keys[-1-offset:-1-offset-THOUGHTS_PAGELEN:-1]
        if comment_keys:
            comments = db.get(comment_keys)
        else:
            comments = []
        logging.debug('my comments: %s' % comments)
        thoughts = [c.thought for c in comments]
    else:
        comments = []
        if keys:
            keys = keys[-1-offset:-1-offset-THOUGHTS_PAGELEN:-1]
            thoughts = db.get(keys)
        else:
            thoughts = []
    
    for t in thoughts:
        add_thought_meta(t, user)
        
    return direct_to_template(request, 'my_thoughts_iframe.html',
                          extra_context={
                                         'uid':xn.uid,
                                         'session_key':xn.session_key,
                                         'thoughts':thoughts,
                                         'comments':comments,
                                         'offset':offset+THOUGHTS_PAGELEN,
                                         'prev_offset':offset-THOUGHTS_PAGELEN,
                                         'has_next':has_next,
                                         'has_prev':has_prev,
                                         'page_len':THOUGHTS_PAGELEN,
                                         'cat':cat,
                                         },)
    
def my_iframe_stuff(request,stuff,offset=0):
    logging.debug('my_iframe got get: %s' % request.GET)
    offset = int(offset)
    xn = request.xiaonei
    xn.check_session(request)
    offset = int(offset)
    user = get_or_create_xnuser(xn)
    if stuff == 'notes':
        obj_list = user.received_notes.order('-date_created').fetch(STUFF_PAGELEN+1, offset)
        for o in obj_list:
            format_datetime(o)
    elif stuff == 'followers':
        keys = user.followers[offset:STUFF_PAGELEN+1]
        if keys:
            obj_list = db.get(keys)
        else:
            obj_list = []
    elif stuff == 'followings':
        keys = user.followings[offset:STUFF_PAGELEN+1]
        if keys:
            obj_list = db.get(keys)
        else:
            obj_list = []
        
    logging.debug('got stuff: %s' % obj_list)
    has_next = len(obj_list) > STUFF_PAGELEN
    obj_list = obj_list[:STUFF_PAGELEN]
    has_prev = offset > 0
    return direct_to_template(request, 'my_stuff_iframe.html',
                          extra_context={
                                         'uid':xn.uid,
                                         'session_key':xn.session_key,
                                         'stuff':stuff,
                                         'offset':offset+STUFF_PAGELEN,
                                         'prev_offset':offset-STUFF_PAGELEN,
                                         'has_next':has_next,
                                         'has_prev':has_prev,
                                         'page_len':STUFF_PAGELEN,
                                         'obj_list':obj_list,
                                         },)
    
@xn.require_add()
def people(request,cat='followers',offset=0):
    if not offset:
        iframe_src = urljoin(settings.SERVER_URL, reverse('people_iframe_def', args=[cat]))
    else:
        iframe_src = urljoin(settings.SERVER_URL, reverse('people_iframe_offset', args=[cat,offset]))
    return direct_to_template(request, 'people.xnml',
                              extra_context={'current':'people',
                                             'cat':cat,
                                             'iframe_src':iframe_src,
                                             },)
    
def people_iframe(request,cat='thoughts',offset=0):
    logging.debug('iframe got get: %s' % request.GET)
    logging.debug('cat: %s' % cat)
    xn = request.xiaonei
    xn.check_session(request)
    user = get_or_create_xnuser(xn)
    logging.debug(u'got user: %s' % user.username)
    offset = int(offset)
    if cat == 'thoughts':
        people = XnUser.all().order('-num_thoughts').fetch(PEOPLE_PAGELEN+1,offset)
    elif cat == 'votes':
        people = XnUser.all().order('-num_votes').fetch(PEOPLE_PAGELEN+1,offset)
    elif cat == 'comments':
        people = XnUser.all().order('-num_comments').fetch(PEOPLE_PAGELEN+1,offset)
    elif cat == 'followers':
        people = XnUser.all().order('-num_followers').fetch(PEOPLE_PAGELEN+1,offset)
    elif cat == 'latest':
        people = XnUser.all().order('-date_joined').fetch(PEOPLE_PAGELEN+1,offset)
        
    logging.debug('got people: %s' % people)
    has_next = len(people) > PEOPLE_PAGELEN
    people = people[:PEOPLE_PAGELEN]
    has_prev = offset > 0
    
    return direct_to_template(request, 'people_iframe.html',
                          extra_context={
                                         'uid':xn.uid,
                                         'session_key':xn.session_key,
                                         'people':people,
                                         'offset':offset+PEOPLE_PAGELEN,
                                         'prev_offset':offset-PEOPLE_PAGELEN,
                                         'has_next':has_next,
                                         'has_prev':has_prev,
                                         'page_len':PEOPLE_PAGELEN,
                                         'cat':cat
                                         },)
    
@xn.require_add()
def profile(request,uid,stuff='thoughts',cat='created',offset=0):
    xn = request.xiaonei
    profile_user = get_user_by_uid(uid)
    if stuff == 'thoughts':
        if offset:
            iframe_src = urljoin(settings.SERVER_URL, reverse('profile_iframe_thoughts_cat_offset', kwargs={'uid':uid,'cat':cat,'offset':offset}))
        else:
            iframe_src = urljoin(settings.SERVER_URL, reverse('profile_iframe_thoughts_def', kwargs={'uid':uid,'cat':cat}))
    else:
        if offset:
            iframe_src = urljoin(settings.SERVER_URL, reverse('profile_iframe_stuff_offset', kwargs={'uid':uid,'stuff':stuff,'offset':offset}))
        else:
            iframe_src = urljoin(settings.SERVER_URL, reverse('profile_iframe_stuff_def', kwargs={'uid':uid,'stuff':stuff}))
        
    #if new note submitted
    post = request.POST
    if post.has_key('note'):
        logging.debug('got new note: %s' % post['note'])
        user = get_or_create_xnuser(xn)
        text = db.Text(post['note'])
        note = Note(from_user=user, to_user=profile_user, content=text)
        note.put()
        #notify profile user
        t = loader.get_template('notify_new_note.xnml')
        c = Context({
                     'uid':xn.uid,
                     'app_url':xn.get_app_url(),
                     'my_url':reverse_xn('my_stuff_def', xn.get_app_url(), args=['notes']),
                     'profile_url':reverse_xn('profile_def', xn.get_app_url(), args=[xn.uid]),
                     })
        msg = t.render(c)
        logging.debug('Sending notification to profile owner for new vote...')
        send_notification(xn,[uid],msg)
        return xn.redirect(reverse_xn('profile_stuff_def', xn.get_app_url(), args=[uid,'notes']))
    
    user = get_or_create_xnuser(xn)
    is_follower = user.key() in profile_user.followers
        
    return direct_to_template(request, 'profile.xnml',
                          extra_context={'current':'profile',
                                         'uid':xn.uid,
                                         'profile_uid':profile_user.uid,
                                         'profile_name':profile_user.username,
                                         'num_thoughts':len(profile_user.my_thoughts),
                                         'num_comments':len(profile_user.comments),
                                         'num_votes':len(profile_user.voted_thoughts),
                                         'iframe_src':iframe_src,
                                         'stuff':stuff,
                                         'cat':cat,
                                         'is_follower':is_follower,
                                         },)
    
def profile_iframe_thoughts(request,uid,cat='created',offset=0):
    logging.debug('profile_iframe got get: %s' % request.GET)
    logging.debug('cat is: %s' % cat)
    offset = int(offset)
    xn = request.xiaonei
    xn.check_session(request)
    user = get_or_create_xnuser(xn)
    profile_user = get_user_by_uid(uid)
    keys= []
    if cat == 'created':
        keys = profile_user.my_thoughts
    elif cat == 'voted':
        keys = profile_user.voted_thoughts
        logging.debug('voted keys: %s' % keys)
    elif cat == 'commented':
        keys = profile_user.comments
    elif cat == 'received':
        keys = profile_user.recommended_thoughts
        
    if not keys:
        has_next = False
    elif keys and offset+THOUGHTS_PAGELEN >= len(keys):
        has_next = False
    else:
        has_next = True
    has_prev = offset > 0
        
    if cat == 'commented':
        comment_keys = keys[-1-offset:-1-offset-THOUGHTS_PAGELEN:-1]
        if comment_keys:
            comments = db.get(comment_keys)
        else:
            comments = []
        thoughts = [c.thought for c in comments]
    else:
        comments = []
        if keys:
            keys = keys[-1-offset:-1-offset-THOUGHTS_PAGELEN:-1]
            if keys:
                thoughts = db.get(keys)
            else:
                thoughts = []
        else:
            thoughts = []
    
    for t in thoughts:
        add_thought_meta(t, user)
        
    return direct_to_template(request, 'profile_thoughts_iframe.html',
                          extra_context={
                                         'uid':xn.uid,
                                         'session_key':xn.session_key,
                                         'profile_user':profile_user,
                                         'profile_uid':profile_user.uid,
                                         'thoughts':thoughts,
                                         'comments':comments,
                                         'offset':offset+THOUGHTS_PAGELEN,
                                         'prev_offset':offset-THOUGHTS_PAGELEN,
                                         'has_next':has_next,
                                         'has_prev':has_prev,
                                         'page_len':THOUGHTS_PAGELEN,
                                         'cat':cat,
                                         },)
    
def profile_iframe_stuff(request,uid,stuff,offset=0):
    logging.debug('profile_iframe got get: %s' % request.GET)
    offset = int(offset)
    xn = request.xiaonei
    xn.check_session(request)
    offset = int(offset)
    profile_user = get_user_by_uid(uid)
    if stuff == 'notes':
        obj_list = Note.all().filter('to_user =',profile_user).order('-date_created').fetch(STUFF_PAGELEN+1, offset)
        for o in obj_list:
            format_datetime(o)
    elif stuff == 'followers':
        keys = profile_user.followers[offset:STUFF_PAGELEN+1]
        if keys:
            obj_list = db.get(keys)
        else:
            obj_list = []
    elif stuff == 'followings':
        keys = profile_user.followings[offset:STUFF_PAGELEN+1]
        if keys:
            obj_list = db.get(keys)
        else:
            obj_list = []
        
    logging.debug('got stuff: %s' % obj_list)
    has_next = len(obj_list) > STUFF_PAGELEN
    obj_list = obj_list[:STUFF_PAGELEN]
    has_prev = offset > 0
    return direct_to_template(request, 'profile_stuff_iframe.html',
                          extra_context={
                                         'uid':xn.uid,
                                         'session_key':xn.session_key,
                                         'stuff':stuff,
                                         'offset':offset+STUFF_PAGELEN,
                                         'prev_offset':offset-STUFF_PAGELEN,
                                         'has_next':has_next,
                                         'has_prev':has_prev,
                                         'page_len':STUFF_PAGELEN,
                                         'obj_list':obj_list,
                                         'profile_uid':profile_user.uid,
                                         },)

@xn.require_add()
def recommend(request, thought_id):
    post = request.POST
    logging.debug('got post: %s' % post)
    to_ids = post.getlist('ids[]')
    logging.debug('got to_ids: %s' % to_ids)
    thought = Thought.get_by_id(int(thought_id))
    xn = request.xiaonei
    if to_ids:
        #send notifications to selected users
        thought_url = reverse_xn('recommend', xn.get_app_url(), args=[thought_id])
        t = loader.get_template('notify_recommend.xnml')
        c = Context({
                     'uid':xn.uid,
                     'thought_url':thought_url,
                     'thought':thought.content,
                     'profile_url':reverse_xn('profile_def', xn.get_app_url(), args=[xn.uid]),
                     })
        msg = t.render(c)
        logging.debug('Sending notification to recommended users...')
        send_notification(xn, to_ids, msg)
        
        #publish feed
        title_data = {
                      'thought_url':thought_url,
                      'thought':thought.content
                      }
        body_data = {'thought_url':thought_url}
        pub_feed(xn, '5', title_data, body_data)
        recommended = True
        
        #save recommend thoughts to existing users
        for id in to_ids:
            user = get_user_by_uid(id)
            if user:
                if thought.key() not in user.recommended_thoughts:
                    logging.debug(u'adding thought to recommended for %s' % user)
                    user.add_recommended(thought)
                    refresh_user_cache(user)
        return xn.redirect(reverse_xn('thought_detail', xn.get_app_url(), args=[thought.key().id()]))
    else:
        recommended = False
    #send notification to selected users
    #if uid is already app user, save thought to his received thoughts
    iframe_src = urljoin(settings.SERVER_URL, reverse('recommend_iframe', args=[thought_id]))
    return direct_to_template(request, 'recommend.xnml',
                          extra_context={
                                         'current':'recommend',
                                         'iframe_src':iframe_src,
                                         'thought_id':thought_id,
                                         'recommended':recommended,
                                         },)

def recommend_iframe(request, thought_id):
    logging.debug('iframe got get: %s' % request.GET)
    xn = request.xiaonei
    xn.check_session(request)
    thought = Thought.get_by_id(int(thought_id))
    if not thought:
        return HttpResponseNotFound()
    logging.debug(u'got thought: %s' % thought)
    user = get_or_create_xnuser(xn)
    add_thought_meta(thought, user)
    return direct_to_template(request, 'recommend_iframe.html',
                          extra_context={
                                         'uid':xn.uid,
                                         'session_key':xn.session_key,
                                         'thought':thought,
                                         },)

def next_comments(request):
    if request.method == 'POST':
        post = request.POST
        logging.debug('got post: %s' % post)
        thought_id = post['thought_id']
        offset = int(post['offset']) + COMMENTS_PAGELEN
        uid = post['uid']
        session_key = post['session_key']
        
        thought = Thought.get_by_id(int(thought_id))
        total_comments = thought.comments[::-1]
        if len(total_comments) > offset:
            logging.debug('getting more comments')
            comments = total_comments[offset:offset+COMMENTS_PAGELEN]
        else:
            logging.debug('getting remaining comments')
            comments = total_comments[-offset:]
        logging.debug('got %s more comments' % len(comments))
        comments = db.get(comments)
        comments.sort(key=lambda x:x.date_created, reverse=True)
        for c in comments:
            if c.author.key() in thought.agreed_users:
                c.agreed = True
            else:
                c.agreed = False
        if offset+COMMENTS_PAGELEN >= len(total_comments):
            has_next = False
        else:
            has_next = True
        t = loader.get_template('next_comments_frag.html')
        c = Context({
                     'comments':comments,
                     'offset':offset,
                     'has_next':has_next,
                     'has_prev':True,
                     'uid':uid,
                     'session_key':session_key,
                     'page_len':COMMENTS_PAGELEN,
                     })
        frag = t.render(c)
        return HttpResponse(frag, mimetype='text/html')
    else:
        return HttpResponseForbidden()
    
def prev_comments(request):
    if request.method == 'POST':
        post = request.POST
        logging.debug('got post: %s' % post)
        thought_id = post['thought_id']
        offset = int(post['offset'])
        uid = post['uid']
        session_key = post['session_key']
        
        thought = Thought.get_by_id(int(thought_id))
        new_offset = offset - COMMENTS_PAGELEN
        if new_offset < 0 :
            new_offset = 0
        total_comments = thought.comments[::-1]
        if new_offset >0:
            logging.debug('getting more comments')
            comments = total_comments[new_offset:offset]
        else:
            logging.debug('getting remaining comments')
            comments = total_comments[:offset]
        logging.debug('got %s more comments' % len(comments))
        comments = db.get(comments)
        comments.sort(key=lambda x:x.date_created, reverse=True)
        for c in comments:
            if c.author.key() in thought.agreed_users:
                c.agreed = True
            else:
                c.agreed = False
        if new_offset > 0:
            has_prev = True
        else:
            has_prev = False
        t = loader.get_template('next_comments_frag.html')
        c = Context({
                     'comments':comments,
                     'offset':new_offset,
                     'has_next':True,
                     'has_prev':has_prev,
                     'uid':uid,
                     'session_key':session_key,
                     'page_len':COMMENTS_PAGELEN,
                     })
        frag = t.render(c)
        return HttpResponse(frag, mimetype='text/html')
    else:
        return HttpResponseForbidden()
    
def next_voters(request):
    if request.method == 'POST':
        post = request.POST
        logging.debug('got post: %s' % post)
        type = post['type']
        thought_id = post['thought_id']
        offset = int(post['offset']) + VOTERS_PAGELEN
        
        thought = Thought.get_by_id(int(thought_id))
        keys = thought.agreed_users if type == 'agrees' else thought.disagreed_users
        keys = keys[-1-offset:-1-offset-VOTERS_PAGELEN-1:-1]
        if len(keys) > VOTERS_PAGELEN:
            has_next = True
        else:
            has_next = False
        #throw away extra key
        voters = db.get(keys[:VOTERS_PAGELEN])
        logging.debug('got voters: %s' % voters)
        
        t = loader.get_template('voters_frag.html')
        c = Context({
                     'voters':voters,
                     'offset':offset,
                     'has_next':has_next,
                     'has_prev':True,
                     'type':type,
                     'page_len':VOTERS_PAGELEN,
                     })
        frag = t.render(c)
        return HttpResponse(frag, mimetype='text/html')
    else:
        return HttpResponseForbidden()

def prev_voters(request):
    if request.method == 'POST':
        post = request.POST
        logging.debug('got post: %s' % post)
        type = post['type']
        thought_id = post['thought_id']
        offset = int(post['offset']) - VOTERS_PAGELEN
        if offset <= 0:
            has_prev = False
            offset = 0
        else:
            has_prev = True
        
        thought = Thought.get_by_id(int(thought_id))
        keys = thought.agreed_users if type == 'agrees' else thought.disagreed_users
        keys = keys[-1-offset:-1-offset-VOTERS_PAGELEN:-1]
        voters = db.get(keys)
        
        t = loader.get_template('voters_frag.html')
        c = Context({
                     'voters':voters,
                     'offset':offset,
                     'has_next':True,
                     'has_prev':has_prev,
                     'type':type,
                     'page_len':VOTERS_PAGELEN,
                     })
        frag = t.render(c)
        return HttpResponse(frag, mimetype='text/html')
    else:
        return HttpResponseForbidden()
    
def vote(request):
    if request.method == 'POST':
        post = request.POST
        logging.debug('got post: %s' % post)
        uid = post['uid']
        user = XnUser.get_by_key_name('uid:'+uid)
        logging.debug(u'got user: %s' % user)
        session_key = post['session_key']
        xn = create_xn_instance(session_key, uid)
        
        thought_id = post['thought_id']
        thought = Thought.get_by_id(int(thought_id))
        type = post['type']
        thought_url = reverse_xn('thought_detail', xn.get_app_url(), args=[thought_id])
        if type == 'agree':
            thought.vote_agree(user)
            user.voted_agree(thought)
            logging.debug('voted agree for %s' % thought.content);
            title_data = {
                          'thought_url':thought_url,
                          'thought':thought.content,
                          }
            body_data = {
                         'thought_url':thought_url,
                         }
            pub_feed(xn, '2', title_data, body_data)
            
        else:
            thought.vote_disagree(user)
            user.voted_disagree(thought)
            logging.debug('voted disagree for %s' % thought.content);
            title_data = {
                          'thought_url':thought_url,
                          'thought':thought.content,
                          }
            body_data = {
                         'thought_url':thought_url,
                         }
            pub_feed(xn, '3', title_data, body_data)
            
        t = loader.get_template('notify_new_vote.xnml')
        c = Context({'uid':xn.uid,
                     'agree': type == 'agree',
                     'thought_url':thought_url,
                     'thought':thought.content,
                     'profile_url':reverse_xn('profile_def', xn.get_app_url(), args=[uid]),
                     })
        msg = t.render(c)
        logging.debug('Sending notification to owner for new vote...')
        send_notification(xn, [thought.owner.uid], msg)
        
        refresh_user_cache(user)
        return HttpResponse(simplejson.dumps({'result':'ok'}), mimetype='application/json')
    else:
        return HttpResponseForbidden()
    
def new_comment(request):
    if request.method == 'POST':
        post = request.POST
        logging.debug('got post: %s' % post)
        uid = post['uid']
        thought_id = post['thought_id']
        content = db.Text(post['comment'])
        session_key = post['session_key']
        user = XnUser.get_by_key_name('uid:'+uid)
        logging.debug(u'got user: %s' % user)
        xn = create_xn_instance(session_key=session_key, uid=uid)
        
        thought = Thought.get_by_id(int(thought_id))
        new_comment = Comment(author=user, thought=thought, content=content)
        new_comment.put()
        thought.add_comment(new_comment)
        user.add_comment(new_comment)
        #return newly added comment html
        t = loader.get_template('new_comment_frag.html')
        c = Context({'c':new_comment,
                     'uid':uid,
                     'session_key':session_key,
                     'thought_id':thought.key().id(),
                     })
        frag = t.render(c)
        refresh_user_cache(user)
        
        #publish feed
        thought_url = reverse_xn('thought_detail', xn.get_app_url(), args=[thought_id])
        title_data = {
                      'thought_url':thought_url,
                      'thought':thought.content,
                      }
        body_data = {
                     'thought_url':thought_url,
                     }
        pub_feed(xn, '4', title_data, body_data)
        
        #send notification to owner
        t = loader.get_template('notify_new_comment.xnml')
        c = Context({'uid':xn.uid,
                     'thought_url':reverse_xn('thought_detail', xn.get_app_url(), args=[thought.key().id()]),
                     'thought':thought.content,
                     'profile_url':reverse_xn('profile_def', xn.get_app_url(), args=[uid]),
                     })
        msg = t.render(c)
        logging.debug('Sending notification to owner for new comment...')
        send_notification(xn, [thought.owner.uid], msg)
        
        return HttpResponse(simplejson.dumps({'frag':frag}), mimetype='application/json')
    else:
        return HttpResponseForbidden()
    
def new_reply(request):
    if request.method == 'POST':
        post = request.POST
        logging.debug('got post: %s' % post)
        uid = post['uid']
        thought_id = post['thought_id']
        comment_id = post['comment_id']
        content = db.Text(post['reply'])
        session_key = post['session_key']
        xn = create_xn_instance(session_key=session_key, uid=uid)
        
        user = XnUser.get_by_key_name('uid:'+uid)
        logging.debug(u'got user: %s' % user)
        thought = Thought.get_by_id(int(thought_id))
        to_comment = Comment.get_by_id(int(comment_id))
        new_reply = Comment(author=user, thought=thought, reply_to=to_comment, content=content)
        new_reply.put()
        to_comment.add_reply(new_reply)
        thought.add_comment(new_reply)
        user.add_comment(new_reply)
        refresh_user_cache(user)
        
        #send notification to owner
        t = loader.get_template('notify_new_reply.xnml')
        c = Context({'uid':xn.uid,
                     'thought_url':reverse_xn('thought_detail', xn.get_app_url(), args=[thought.key().id()]),
                     'thought':thought.content,
                     'profile_url':reverse_xn('profile_def', xn.get_app_url(), args=[uid]),
                     })
        msg = t.render(c)
        logging.debug('Sending notification to owner for new reply...')
        send_notification(xn, [to_comment.author.uid], msg)
        
        return HttpResponse(simplejson.dumps({'result':'ok'}), mimetype='application/json')
    else:
        return HttpResponseForbidden()
        
def get_replies(request):
    if request.method == 'POST':
        post = request.POST
        logging.debug('got post: %s' % post)
        session_key = post['session_key']
        uid = post['uid']
        comment_id = post['comment_id']
        comment = Comment.get_by_id(int(comment_id))
        replies = comment.replies_list
        if replies:
            replies = db.get(replies)
            replies.sort(key=lambda x:x.date_created, reverse=True)
            for r in replies:
                if r.author.key() in comment.thought.agreed_users:
                    r.agreed = True
                    r.voted = True
                elif r.author.key() in comment.thought.disagreed_users:
                    r.agreed = False
                    r.voted = True
                else:
                    r.agree = False
                    r.voted = False
            t = loader.get_template('replies_frag.html')
            c = Context({
                         'replies':replies,
                         'session_key':session_key,
                         'uid':uid
                         })
            frag = t.render(c)
            return HttpResponse(frag, mimetype='text/html')
        else:
            return HttpResponseBadRequest()
    else:
        return HttpResponseForbidden()
    
@xn.require_add()
def follow_user(request, to_uid, from_uid):
    xn = request.xiaonei
    logging.debug('got to_uid: %s' % to_uid)
    logging.debug('got from_uid: %s' % from_uid)
    if from_uid and to_uid:
        follower = get_user_by_uid(from_uid)
        followed = get_user_by_uid(to_uid)
        if follower and followed:
            follower.add_following(followed)
            followed.add_follower(follower)
            refresh_user_cache(follower)
            refresh_user_cache(followed)
            #send notification to owner
            t = loader.get_template('notify_new_follower.xnml')
            c = Context({'uid':xn.uid,
                         'profile_url':reverse_xn('profile_def', xn.get_app_url(), args=[xn.uid]),
                         })
            msg = t.render(c)
            logging.debug('Sending notification to owner for new follower...')
            send_notification(xn, [to_uid], msg)
            return xn.redirect(reverse_xn('profile_def',xn.get_app_url(),args=[to_uid]))
        else:
            return HttpResponseBadRequest()
    else:
        return HttpResponseBadRequest()
    
@xn.require_add()
def invite(request):
    return direct_to_template(request, 'invite.xnml',
                          extra_context={'current':'invite'
                                         })
    
def get_session_info(request):
    logging.debug('iframe got get: %s' % request.GET)
    get = request.GET
    session_key = get.get('xn_sig_session_key','')
    uid = get.get('xn_sig_user','')
    if session_key and uid:
        session_info = SessionInfo.all().filter('uid =', uid).get()
        if not session_info:
            session_info = SessionInfo(session_key=session_key,uid=uid)
            session_info.put()
            logging.debug(u'saved new session_info: %s' % session_info)
        else:
            logging.debug('session_info already existing for: %s' % uid)
            session_info.session_key = session_key
            session_info.put()
            logging.debug('session_info updated')
    return HttpResponse('ok', mimetype='text/html')

APPS = ['buddywall','bestfriends','storywar','agreeornot','comparefriends','tagfriends','xiaoxun']
APPLINKS = {
            'buddywall':'http://apps.xiaonei.com/buddywall/',
            'bestfriends':'http://apps.xiaonei.com/bestfriends/',
            'storywar':'http://apps.xiaonei.com/storywar/',
            'agreeornot':'http://apps.xiaonei.com/agreeornot/',
            'comparefriends':'http://apps.xiaonei.com/comparefriends/login',
            'tagfriends':'http://apps.xiaonei.com/tagfriends/login',
            'xiaoxun':'http://apps.xiaonei.com/xiaoxun',
            }

def promote(request):
    referer = request.META.get('HTTP_REFERER','')
    logging.debug('got referer: %s' % request.META.get('HTTP_REFERER',''))
    choice = random.choice(APPS)
    logging.debug('initial choice is: %s' % choice)
    if choice in referer:
        logging.debug('do not show ad for current app')
        list = APPS[:]
        list.remove(choice)
        choice = random.choice(list)
    logging.debug('PROMTE choice: %s' % choice)
#    while referer.find(choice):
#        choice = random.choice(APPS)
    link = APPLINKS[choice]
    return direct_to_template(request, 'promote.html',
                      extra_context={'choice':choice,
                                     'link':link,
                                     })
    
def error_500(request):
    """ Custom exception handler for Django.
    
    Note that settings.DEBUG must be False or
    this handler is never run.
    """
    
    # Get the latest exception from Python system service
    exception = sys.exc_info()[0]
    
    # Use  Python logging module to log the exception
    # For more information see:
    # http://docs.python.org/lib/module-logging.html
    logging.error("Uncaught exception got through, rendering 500 page")
    logging.error("Exception is DownloadError? %s" % isinstance(exception, DownloadError)) 
    logging.exception(exception)
    
    spurl = random.choice(SP_IMGS)
        # Output user visible HTTP response
    return direct_to_template(request, '500.html',
                              extra_context={'img':spurl,})
#    return HttpResponseServerError(render_to_string("500.html"))