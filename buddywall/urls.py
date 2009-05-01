from django.conf.urls.defaults import *

urlpatterns = patterns('',
    url(r'^xn/', include('buddywall.urls')),
)

handler500 = 'buddywall.views.error_500'