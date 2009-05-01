from django import template
from django.conf import settings
from django.core.urlresolvers import reverse
from django.template.defaulttags import URLNode
from urlparse import urljoin
from django.template import TemplateSyntaxError
from buddywall import urls

register = template.Library()

class XiaoneiURL(URLNode):
    def __init__(self, view_name, args, kwargs, asvar):
        URLNode.__init__(self, view_name, args, kwargs, asvar)
        self.app_name = getattr(settings, "XIAONEI_APP_NAME", "appname")
        self.fb_callback = getattr(settings, "XIAONEI_CALLBACK_PATH", "")
    def render(self, context):
        url = URLNode.render(self, context).replace(self.fb_callback, '')
        return urljoin("http://apps.xiaonei.com/%s/" % self.app_name, url)
    
@register.tag(name='xnurl')
def xnurl(parser, token):
    """
    renders a xiaonei apps url instead of the url of your own server
    """
    bits = token.contents.split(' ')
    if len(bits) < 2:
        raise TemplateSyntaxError("'%s' takes at least one argument"
                                  " (path to a view)" % bits[0])
    viewname = bits[1]
    args = []
    kwargs = {}
    asvar = None
        
    if len(bits) > 2:
        bits = iter(bits[2:])
        for bit in bits:
            if bit == 'as':
                asvar = bits.next()
                break
            else:
                for arg in bit.split(","):
                    if '=' in arg:
                        k, v = arg.split('=', 1)
                        k = k.strip()
                        kwargs[k] = parser.compile_filter(v)
                    elif arg:
                        args.append(parser.compile_filter(arg))
    return XiaoneiURL(viewname, args, kwargs, asvar)

@register.filter
def EQ(value,arg): return value == arg

@register.filter
def LT(value,arg): return value < arg

@register.filter
def GT(value,arg): return value > arg

@register.filter
def LE(value,arg): return value <= arg

@register.filter
def GE(value,arg): return value >= arg

@register.filter
def NE(value,arg): return value != arg

@register.filter
def IS(value,arg): return value is arg

@register.filter
def IN(value,arg): return value in arg