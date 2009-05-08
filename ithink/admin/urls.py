from django.conf.urls.defaults import *

urlpatterns = patterns('admin.views',
    url(r'^$', 'home', name="admin_home"),
)