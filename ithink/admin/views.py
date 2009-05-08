from django.views.generic.simple import direct_to_template
from google.appengine.api import users
from django.http import HttpResponseRedirect
from django.core.urlresolvers import reverse
from ithink.models import Thought, Feature
import logging
from google.appengine.ext import db

def home(request):
    logging.debug('admin home page')
    cur_user = users.get_current_user()
    logging.debug('current user: %s' % cur_user)
    if not cur_user:
        return HttpResponseRedirect(users.create_login_url(reverse('admin_home')))
    else:
        if request.method == 'POST':
            post = request.POST
            logging.debug('got post: %s' % post)
            id = post.get('set_featured','')
            if id:
                thought = Thought.get_by_id(int(id))
                if thought:
                    feature = Feature(thought=thought)
                    feature.put()
        thoughts = Thought.all().order('-date_created').fetch(100)
        for t in thoughts:
            t.date_created_str = t.date_created.strftime('%Y-%m-%dT%H:%M:%SZ')
        latest_feature = Feature.all().order('-date_created').get()
        return direct_to_template(request, 'admin/home.html',
                              extra_context={'current':'home',
                                             'g_user': cur_user,
                                             'logout_url': users.create_logout_url(reverse('admin_home')),
                                             'thoughts':thoughts,
                                             'latest_feature':latest_feature,
                                             },)
