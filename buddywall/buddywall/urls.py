from django.conf.urls.defaults import *

urlpatterns = patterns('buddywall.views',
    url(r'^$', 'canvas', name="canvas"),
    url(r'^whohasme/$', 'who_has_me', name="who_has_me"),
    url(r'^refresh/$', 'refresh_wall', name='refresh_wall'),
    url(r'^notify/$', 'notify', name='notify'),
    url(r'^getinfo/$', 'get_user_info', name='get_user_info'),
    url(r'^choosebg/$', 'choose_bg', name='choose_bg'),
    url(r'^setbg/$', 'set_bg', name='set_bg'),
    url(r'^postinvite/$', 'post_invite', name='post_invite'),
    url(r'^invite/$', 'invite', name='invite'),
    url(r'^stats/$', 'stats', name='stats'),
)