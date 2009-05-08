/*
 * timeago: a jQuery plugin, version: 0.4 (08/05/2008)
 * @requires jQuery v1.2 or later
 *
 * Timeago is a jQuery plugin that makes it easy to support automatically
 * updating fuzzy timestamps (e.g. "4 minutes ago" or "about 1 day ago").
 *
 * For usage and examples, visit:
 * http://timeago.yarp.com/
 *
 * Licensed under the MIT:
 * http://www.opensource.org/licenses/mit-license.php
 *
 * Copyright (c) 2008, Ryan McGeary (ryanonjavascript -[at]- mcgeary [*dot*] org)
 */
(function($) {
  $.timeago = function(timestamp) {
    if (timestamp instanceof Date) return inWords(timestamp);
    else if (typeof timestamp == "string") return inWords($.timeago.parse(timestamp));
    else return inWords($.timeago.parse($(timestamp).attr("title")));
  };

  $.extend($.timeago, {
    settings: {
      refreshMillis: 60000,
      allowFuture: false
    },
    inWords: function(distanceMillis) {
      var suffix = "前";
      if (this.settings.allowFuture) {
        if (distanceMillis < 0) suffix = "从现在起";
        distanceMillis = Math.abs(distanceMillis);
      }

      var seconds = distanceMillis / 1000;
      var minutes = seconds / 60;
      var hours = minutes / 60;
      var days = hours / 24;
      var years = days / 365;

      var words = seconds < 45 && "不到1分钟" ||
        seconds < 90 && "大约1分钟" ||
        minutes < 45 && Math.round(minutes) + "分钟" ||
        minutes < 90 && "大约1小时" ||
        hours < 24 && "大约 " + Math.round(hours) + "小时" ||
        hours < 48 && "一天" ||
        days < 30 && Math.floor(days) + "天" ||
        days < 60 && "大约一个月" ||
        days < 365 && Math.floor(days / 30) + "个月" ||
        years < 2 && "大约一年" ||
        Math.floor(years) + "年";

      return words + suffix;
    },
    parse: function(iso8601) {
      var s = $.trim(iso8601);
      s = s.replace(/-/,"/").replace(/-/,"/");
      s = s.replace(/T/," ").replace(/Z/," UTC");
      s = s.replace(/([\+-]\d\d)\:?(\d\d)/," $1$2"); // -04:00 -> -0400
      return new Date(s);
    }
  });

  $.fn.timeago = function() {
    var self = this;
    self.each(refresh);

    var $s = $.timeago.settings;
    if ($s.refreshMillis > 0) {
      setInterval(function() { self.each(refresh); }, $s.refreshMillis);
    }
    return self;
  };

  function refresh() {
    var date = $.timeago.parse(this.title);
    if (!isNaN(date)) {
      $(this).text(inWords(date));
    }
    return this;
  }

  function inWords(date) {
    return $.timeago.inWords(distance(date));
  }

  function distance(date) {
    return (new Date().getTime() - date.getTime());
  }
})(jQuery);

