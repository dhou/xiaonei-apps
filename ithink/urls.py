from django.conf.urls.defaults import *

urlpatterns = patterns('',
    url(r'^xn/', include('ithink.urls')),
    url(r'^admin/', include('admin.urls')),
)

handler500 = 'ithink.views.error_500'