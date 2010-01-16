#!/usr/bin/env python

# Copyright (c) 2009 Johan Uhle
# 
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
# 
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

from google.appengine.ext import webapp

import logging

import scapi
import settings

class SoundCloudConnectFavoritesHandler(webapp.RequestHandler):
  def get(self):
    sid = self.request.cookies.get("sid")
    logging.info("SID: " + sid)
    sid_data = models.OAuthToken.all().filter('session_hash', sid).get()
    logging.info("sid_data: " + str(sid_data))
    oauth_authenticator = scapi.authentication.OAuthAuthenticator(settings.OAUTH_CONSUMER_KEY, 
                                                                  settings.OAUTH_CONSUMER_SECRET,
                                                                  sid_data.token, 
                                                                  sid_data.secret)                                                                  
    root = scapi.Scope(scapi.ApiConnector(host=settings.SOUNDCLOUD_API_URL, authenticator=oauth_authenticator))
    favorites = list(root.me().favorites())
    
    self.response.out.write(favorites)
    
    # for follower in followers[0:10]:
    #   logging.info(follower)      
    #   try:
    #     geocached_location = backend_utils.get_location(follower['city'], follower['country'])
    #   
    #     if geocached_location['city'] == 'None' or geocached_location['country'] == 'None' or \
    #     geocached_location['city'] == None or geocached_location['country'] == None:   
    #       logging.info("No Location")
    #       continue
    #     else:
    #       logging.info(geocached_location)
    #   except RuntimeError:
    #     logging.info("No Location")
    #     pass