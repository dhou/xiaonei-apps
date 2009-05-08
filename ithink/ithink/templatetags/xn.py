from django import template
from django.conf import settings
from django.core.urlresolvers import reverse
from django.template.defaulttags import URLNode
from urlparse import urljoin
from django.template import TemplateSyntaxError, Node, NodeList, Variable,\
    VariableDoesNotExist
import os.path
import md5

register = template.Library()

class XiaoneiURL(URLNode):
    def __init__(self, view_name, args, kwargs):
        URLNode.__init__(self, view_name, args, kwargs)
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
    bits = token.contents.split(' ', 2)
    if len(bits) < 2:
        raise TemplateSyntaxError("'%s' takes at least one argument"
                                  " (path to a view)" % bits[0])
    args = []
    kwargs = {}
    if len(bits) > 2:
        for arg in bits[2].split(','):
            if '=' in arg:
                k, v = arg.split('=', 1)
                k = k.strip()
                kwargs[k] = parser.compile_filter(v)
            else:
                args.append(parser.compile_filter(arg))
    return XiaoneiURL(bits[1], args, kwargs)

@register.simple_tag
def versioned_url(url):
    path = os.path.join(settings.MEDIA_ROOT,url);
    if os.path.exists(path):
        return urljoin(settings.MEDIA_URL,url)+'?%s' % int(os.path.getmtime(path))
    else:
        return url
    
@register.simple_tag
def abs_url(url):
    return urljoin(settings.SERVER_URL, url)

class RangeNode(Node):
    def __init__(self, num, context_name):
        self.num, self.context_name = num, context_name
    def render(self, context):
        context[self.context_name] = range(int(self.num))
        return ""
        
@register.tag
def num_range(parser, token):
    """
    Takes a number and iterates and returns a range (list) that can be 
    iterated through in templates
    
    Syntax:
    {% num_range 5 as some_range %}
    
    {% for i in some_range %}
      {{ i }}: Something I want to repeat\n
    {% endfor %}
    
    Produces:
    0: Something I want to repeat 
    1: Something I want to repeat 
    2: Something I want to repeat 
    3: Something I want to repeat 
    4: Something I want to repeat
    """
    try:
        fnctn, num, trash, context_name = token.split_contents()
    except ValueError:
        raise TemplateSyntaxError, "%s takes the syntax %s number_to_iterate\
            as context_variable" % (fnctn, fnctn)
    if not trash == 'as':
        raise TemplateSyntaxError, "%s takes the syntax %s number_to_iterate\
            as context_variable" % (fnctn, fnctn)
    return RangeNode(num, context_name)

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

class SwitchNode(template.Node):
    def __init__(self, var1, nodelist_true, nodelist_false):
        self.comparison_base = Variable(var1)
        self.nodelist_true = nodelist_true
        self.nodelist_false = nodelist_false
        self.varname = var1
        
    def __repr__(self):
        return "<SwitchNode>"

    def render(self, context):
        try:
            val1 = self.comparison_base.resolve(context)
            bhash = "__%s__" % md5.new(self.varname).hexdigest()
            context[bhash] =  val1
        except VariableDoesNotExist:
            raise TemplateSyntaxError("Could not resolve variable %r in current context" % \
                                      self.comparison_base.var)
        ok = False
        for node in self.nodelist_true:
            if isinstance(node, CaseNode):
                node.set_source(bhash)
                if node.get_bool(context):
                    ok = True
        if ok:
            return self.nodelist_true.render(context)
        else:
            return self.nodelist_false.render(context)

@register.tag    
def switch(parser, token):
    """
    Create a context to use case-like coditional
    template rendering.

    For example::

        {% switch person.name %}
            {% case 'John Doe' %}
                Hi! My name is John, the master!
            {% endcase %}
            {% case 'Mary Jane' %}
                Hello! My name is Mary. Nice to meet you!
            {% endcase %}            
        {% default %}
            Oh my God! I have no name!
        {% endswitch %}
    """
    
    bits = list(token.split_contents())
    if len(bits) != 2:
        raise TemplateSyntaxError, "%r takes one argument" % bits[0]
    end_tag = 'end' + bits[0]
    nodelist_true = parser.parse(('default', end_tag,))
    token = parser.next_token()
    if token.contents == 'default':
        nodelist_false = parser.parse((end_tag,))
        parser.delete_first_token()
    else:
        nodelist_false = NodeList()
    return SwitchNode(bits[1], nodelist_true, nodelist_false)


class CaseNode(Node):
    def __init__(self, var, nodelist):
        self.var = Variable(var)
        self.nodelist = nodelist
        
    def __repr__(self):
        return "<CaseNode>"
    
    def set_source(self, var):
        """ Sets the varname to lookup in
        context and make the comparisons"""
        self.base_comparison = var
        
    def get_bool(self, context):
        try:
            val = self.var.resolve(context)
        except VariableDoesNotExist:
            val = None
            
        base_comparison = getattr(self, "base_comparison", None)
        if not base_comparison:
            raise LookupError("Could not find base_comparison. "
                              "Ensure to use {% case %} node "
                              "within a {% switch %} node")
        if context.get(self.base_comparison, None) == val:
            return True
        else:
            return False
        
    def render(self, context):
        if self.get_bool(context):
            return self.nodelist.render(context)
        else:
            return NodeList().render(context)


@register.tag    
def case(parser, token):
    bits = list(token.split_contents())
    if len(bits) != 2:
        raise TemplateSyntaxError, "%r takes one argument" % bits[0]
    end_tag = 'end' + bits[0]
    nodelist_true = parser.parse(('else', end_tag))
    token = parser.next_token()
    if token.contents == 'else':
        nodelist_false = parser.parse((end_tag,))
        parser.delete_first_token()
    else:
        nodelist_false = NodeList()
    return CaseNode(bits[1], nodelist_true)
