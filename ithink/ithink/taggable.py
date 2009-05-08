# -*- coding: utf-8 -*-
#Copyright 2008 Adam A. Crossland
#
#Licensed under the Apache License, Version 2.0 (the "License");
#you may not use this file except in compliance with the License.
#You may obtain a copy of the License at
#
#http://www.apache.org/licenses/LICENSE-2.0
#
#Unless required by applicable law or agreed to in writing, software
#distributed under the License is distributed on an "AS IS" BASIS,
#WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#See the License for the specific language governing permissions and
#limitations under the License.

from google.appengine.ext import db
from google.appengine.ext import gql
from google.appengine.ext.db import GqlQuery
from copy import copy
import math
import re
import string
import logging

        
# Font size distribution algorithms
LOGARITHMIC, LINEAR = 1, 2

class Tag(db.Model):
    "Google AppEngine model for store of tags."
    tag = db.StringProperty(required = True)
    "The actual string value of the tag."
    date_created = db.DateTimeProperty(auto_now_add = True)
    "The date and time that the tag was first added to the datastore."
    tagged = db.ListProperty(db.Key)
    "A List of db.Key values for the datastore objects that have been tagged with this tag value."
    num_tagged = db.IntegerProperty(default=1)
    
    def __unicode__(self):
        return u'%s' % self.tag
    
    @staticmethod
    def get_tags_for(key):
        "Get the tags for the datastore object represented by key."
#        tags = GqlQuery("SELECT * FROM Tag WHERE tagged = :1", key)
        tags = Tag.all().filter('tagged =', key).order('-num_tagged').fetch(50)
        return tags
#    Get_Tags_For = staticmethod(get_tags_for)

    @staticmethod
    def get_by_tag_value(tag_value):
        "Get the Tag object that has the tag value given by tag_value."
        # There should only ever be one record in the datastore for a given tag value.
        return Tag.all().filter('tag =', tag_value).get()
#    Get_By_Tag_Value = staticmethod(get_by_tag_value)

    @staticmethod
    def set_tags_for(key, tag_list):
        "Apply the tags in the List tag_list to the datastore object represented by key."
        for each_tag in tag_list:
            # Make sure that we don't have any leading or trailing whitespace
            each_tag = string.strip(each_tag)
            existing_tag = Tag.gql("WHERE tag = :1", each_tag).get()
            if not existing_tag:
                # This tag is not yet in the datastore, so create it, add the key and save it.
                tagged_list = []
                tagged_list.append(key)
                new_tag = Tag(tag = each_tag, tagged = tagged_list)
                new_tag.put()
            else:
                # The tag already exists, add the new key and save.
                if key not in existing_tag.tagged:
                    existing_tag.tagged.append(key)
                    existing_tag.num_tagged += 1
                    existing_tag.put()
#    Set_Tags_For = staticmethod(set_tags_for)

    @staticmethod
    def get_tags_by_frequency(min_count=1, limit = 0):
        """Return a list of Tags sorted by the number of objects to which they have been applied,
        most frequently-used first.  If limit is given, return only that many tags; otherwise,
        return all."""
        fetch_limit = limit if limit>0 else 1000
        tag_list = Tag.all().filter('num_tagged >=',min_count).order('-num_tagged').fetch(fetch_limit)
        if limit > 0:
            tag_list = tag_list[:limit]
            
        return tag_list
#    Get_Tags_By_Frequency = staticmethod(get_tags_by_frequency)
    
    @staticmethod
    def get_cloud(steps, min_count=1, limit=0, distribution=LOGARITHMIC):
        tags = Tag.get_tags_by_frequency(min_count, limit)
        return calculate_cloud(tags, steps, distribution)

def sort_by_frequency(tag_a, tag_b):
    comp = 0 # Assume equality
    if len(tag_a.tagged) > len(tag_b.tagged):
        comp = -1
    elif len(tag_a.tagged) < len(tag_b.tagged):
        comp = 1
        
    return comp

class Taggable:
    """A mixin class that is used for making Google AppEnigne Model classes taggable.
        Usage:
            class Post(db.Model, taggable.Taggable):
                body = db.TextProperty(required = True)
                title = db.StringProperty()
                added = db.DateTimeProperty(auto_now_add=True)
                edited = db.DateTimeProperty()
            
                def __init__(self, parent=None, key_name=None, app=None, **entity_values):
                    db.Model.__init__(self, parent, key_name, app, **entity_values)
                    taggable.Taggable.__init__(self)
    """
    
    def __init__(self):
        self.tags = None
        "A List of the tags for this object.  Populated by get_tags()."
        self.tag_string = ""
        "A string representation of the list of tags for this object.  Populated by get_tags_as_string()."
        self.tag_seperator = ","
        "The string that is used to separate individual tags in a string representation of a list of tags."
        self.spliter = re.compile(u'[,，  ]')

    def get_tags(self):
        "Get a List of Tag objects for all Tags that apply to this object."
#        tags_list = Tag.get_tags_for(self.key())
#        if tags_list != None:
#            for each_tag in tags_list:
#                if self.tags == None:
#                    self.tags = []
#                self.tags.append(each_tag)
#        return self.tags
        return Tag.get_tags_for(self.key())
    
    def get_tags_as_string(self):
        "Create a string representation of all of the tags that apply to this object."
#        if self.tags == None:
#            # We build the string using the tags property, so we need to make sure that it has been populated.
#            self.get_tags()
#        tags_as_string = ""
#        if self.tags != None:
#            for each_tag in self.tags:
#                if len(tags_as_string) != 0:
#                    tags_as_string += self.tag_seperator
#                tags_as_string += each_tag.tag
#            self.tag_string = tags_as_string
#                
#        return tags_as_string
        tags = self.get_tags()
        return self.tag_seperator.join(tags) if tags else ''
    
    def __repr__(self):
        if (self.tag_string == None) or (len(self.tag_string) == 0):
            # If there isn't a value yet in tag_string, call get_tags_as_string to
            # populate it.  After the call, it might still be empty, but we know at least
            # that it is empty because there are no tags for this object.
            self.get_tags_as_string()
            
        return self.tag_string
    
    def set_tags(self, tag_list):
        "Set the tags for the Taggable object from a list of strings."
        for each_tag in tag_list:
            # We need to call strip on each tag string, as leading and trailing
            # whitespace is very likely. We don't want to end up with
            # tags that are dupes of others because they have whitespace.
            each_tag = string.strip(each_tag)
            # It is possible that we could receive a tag_list array that has an empty member;
            # this could happen because of two consecutive seperators or a list that ends
            # with a seperator.  Check and skip processing such list elements.
            if len(each_tag) > 0:
                existing_tag = Tag.get_by_tag_value(each_tag)
                if existing_tag == None:
                    # This tag does not yet exist in the datastore, so create it,
                    # set the tags and put it in the store.
#                    tagged_list = []
#                    tagged_list.append(self.key())
                    new_tag = Tag(tag = each_tag, tagged = [self.key(),])
                    new_tag.put()
                else:
                    # This tag is already in the datastore.  If the object is not
                    # already in the tagged list, add it.  Otherwise, do nothing;
                    # we're good!
                    if (self.key() not in existing_tag.tagged):
                        existing_tag.tagged.append(self.key())
                        existing_tag.num_tagged += 1
                        existing_tag.put()
        
    def set_tags_from_string(self, tag_list):
        """Set the tags for the Taggable object from a string that contains one or more
        tags seperated by the character or charaters in self.tag_seperator."""
#        tags = string.split(tag_list, self.tag_seperator)
        tags = self.spliter.split(tag_list)
        self.set_tags(tags)
        
#    def get_related_objs(self):
#        tags = self.get_tags()


def _calculate_thresholds(min_weight, max_weight, steps):
    delta = (max_weight - min_weight) / float(steps)
    return [min_weight + i * delta for i in range(1, steps + 1)]

def _calculate_tag_weight(weight, max_weight, distribution):
    """
    Logarithmic tag weight calculation is based on code from the
    `Tag Cloud`_ plugin for Mephisto, by Sven Fuchs.

    .. _`Tag Cloud`: http://www.artweb-design.de/projects/mephisto-plugin-tag-cloud
    """
    if distribution == LINEAR or max_weight == 1:
        return weight
    elif distribution == LOGARITHMIC:
        return math.log(weight) * max_weight / math.log(max_weight)
    raise ValueError(_('Invalid distribution algorithm specified: %s.') % distribution)

def calculate_cloud(tags, steps=4, distribution=LOGARITHMIC):
    """
    Add a ``font_size`` attribute to each tag according to the
    frequency of its use, as indicated by its ``count``
    attribute.

    ``steps`` defines the range of font sizes - ``font_size`` will
    be an integer between 1 and ``steps`` (inclusive).

    ``distribution`` defines the type of font size distribution
    algorithm which will be used - logarithmic or linear. It must be
    one of ``tagging.utils.LOGARITHMIC`` or ``tagging.utils.LINEAR``.
    """
    if len(tags) > 0:
        counts = [tag.num_tagged for tag in tags]
        min_weight = float(min(counts))
        max_weight = float(max(counts))
        thresholds = _calculate_thresholds(min_weight, max_weight, steps)
        for tag in tags:
            tag.font_size = 0
            font_set = False
            tag_weight = _calculate_tag_weight(tag.num_tagged, max_weight, distribution)
            for i in range(steps):
                if not font_set and tag_weight <= thresholds[i]:
                    tag.font_size = i + 1
                    font_set = True
    return tags