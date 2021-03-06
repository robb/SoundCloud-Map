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
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.ext import db             
from google.appengine.ext.webapp import template
from google.appengine.api import memcache
from django.utils import simplejson as json

import logging
import os
import urllib
import re
import datetime

import models
import utils
import settings

def create_location_dict(location):
   location_dict = {'lon': location.location.lon,
                   'lat': location.location.lat,
                   'id' : location.key().id(),
                   'city': location.city,
                   'country': location.country,
                   'track_counter': location.track_counter,
                   'last_time_updated': location.last_time_updated.isoformat(' ')}   
   return location_dict

def add_to_track_array(track, track_array): 
  """
    filling an array with all the track, location and user data per track 
  """
  location_dict = create_location_dict(track.user.location)
  
  user_dict = {'id': track.user.user_id,
               'permalink': track.user.permalink,
               'permalink_url': track.user.permalink_url,
               'username': track.user.username,
               'fullname': track.user.fullname,
               'avatar_url': track.user.avatar_url}
   
  track_array.append({  'error': False,
                        'id': track.track_id,
                        'permalink': track.permalink, 
                        'permalink_url': track.permalink_url, 
                        'title': track.title,
                        \
                        'waveform_url': track.waveform_url,
                        'stream_url': track.stream_url, 
                        'artwork_url': track.artwork_url,
                        \
                        'created_at': track.created_at.isoformat(' '),
                        'created_minutes_ago': track.created_minutes_ago(),
                        'downloadable': track.downloadable,
                        'license': track.license,
                        'genre': track.genre,
                        'duration': track.duration,
                        \
                        'location': location_dict,
                        'user': user_dict})                            

def memcache_and_output_array(self, array, xspf_prefix="latest", time=(settings.API_QUERY_INTERVAL*60-5)):  
  """
    Save to memcache and output as plain json
  """ 
  self.response.headers.__delitem__('Cache-Control')
  self.response.headers.add_header('Cache-Control', ('max-age='+str(60)))  
  logging.info(self.request.path)
  if self.request.path.replace("/","").split(".")[-1] == "xspf":
    self.response.headers["Content-Type"] = "application/xspf+xml"
    self.response.headers.add_header('Content-Disposition', 'attachment', filename=xspf_prefix+'_tracksonamap.xspf')
    
    path = os.path.join(os.path.dirname(__file__), 'templates/xspf')
    output = template.render(path, { 'array' : array, 
                                     'prefix' : xspf_prefix.replace("_", " ").title(), 
                                     'date' : datetime.datetime.now().isoformat() })
  else:
    output = json.dumps(array)  
  memcache.add(self.request.path_qs, output, time=time, namespace='api_cache')
  self.response.out.write(output)                          
  return

def error_response(self, error_name, error_description):
  """
    Output error as json  
  """
  error_response = {'error': True, 'error_name': error_name, 'error_description': error_description}
  self.response.out.write(json.dumps(error_response))

def fetch_location_by_id(self, location_id): 
  """
    Return location_array with only one location for location_id
  """
  locations_array = []
  location = models.Location.get_by_id(int(location_id))
  if location:
    locations_array.append(create_location_dict(location))
    return memcache_and_output_array(self, locations_array)
  else:
    error_response(self, 'location_not_found', 'The location with the location_id %s is not in the datastore.' % location_id)
  return
 
def fetch_track_by_id(self, track_id): 
  """
    Return track_array with only one track for track_id
  """
  track_array = []
  track = models.Track.all().filter('track_id', int(track_id)).get()
  if track:
    add_to_track_array(track, track_array)
    return memcache_and_output_array(self, track_array)
  else:
    error_response(self, 'track_not_found', 'The track with the track_id %s is not in the datastore.' % track_id)
  return     
           
class TracksHandler(webapp.RequestHandler):
  """
    Fetching tracks. Returning json
  """
  def get(self):
                                              
    memcached = memcache.get(self.request.path_qs, namespace='api_cache' )
    if memcached is not None and not utils.in_development_enviroment():
      return self.response.out.write(memcached)
                          
    # initializing
    track_array = []
    if self.request.get('limit'):
      limit = int(self.request.get('limit'))
    else:
      limit = settings.FRONTEND_LOCATIONS_LIMIT          
    if self.request.get('offset'):
      offset = int(self.request.get('offset'))
    else:
      offset = 0
    
    # Processing for api/tracks/?track=track_id
    if self.request.get('track'):
      return fetch_track_by_id(self, self.request.get('track'))
    
    # Processing for api/tracks/?genre={genre_name} 
    if self.request.get('genre') and self.request.get('genre') != 'all' and not \
       (self.request.get('location') or self.request.get('location_lat') or self.request.get('location_lon')):
      genre = self.request.get('genre')
      if genre not in utils.genres:
        error_response(self, 'unknown_genre', 'Sorry, but we do not know the genre %s.' % genre) 
        return
      else:
        tracks = models.Track.all().filter('genre IN', utils.genres.get(genre)).order('-created_at').fetch(limit, offset)
        if tracks:                           
          for track in tracks:
            add_to_track_array(track, track_array)
          return memcache_and_output_array(self, track_array, utils.genres.get(genre)[0])
        else:
          self.response.out.write("[]") # empty array
        return           
    
    # Processing for api/tracks/?location=location_id
    if self.request.get('location') and (self.request.get('genre') == 'all' or not self.request.get('genre')): 
      location = models.Location.get_by_id(int(self.request.get('location')))
      if not location:
        error_response(self, 'location_not_found', 'The location with the id %s is not in the datastore.' % self.request.get('location'))
      else:
        tracks = models.Track.all().filter('location', location.key()).order('-created_at').fetch(limit, offset)
        if tracks:
          for track in tracks:
            add_to_track_array(track, track_array)              
          return memcache_and_output_array(self, track_array, location.city)
        else:
          self.response.out.write("[]") # empty array
      return
      
    # Processing for api/tracks/?location=location_id&genre={genre_name}  
    if self.request.get('location') and self.request.get('genre'):
      genre = self.request.get('genre')
      if genre not in utils.genres:
        error_response(self, 'unknown_genre', 'Sorry, but we do not know the genre %s.' % genre) 
        return
      location = models.Location.get_by_id(int(self.request.get('location')))
      if not location:
        error_response(self, 'location_not_found', 'The location with the id %s is not in the datastore.' % self.request.get('location'))
        return
      else:
        tracks = models.Track.all().filter('location', location.key()).filter('genre IN', utils.genres.get(genre))
        tracks = tracks.order('-created_at').fetch(limit, offset)
        if tracks:
          for track in tracks:
            add_to_track_array(track, track_array)              
          return memcache_and_output_array(self, track_array, (location.city + "_" + utils.genres.get(genre)[0]))
        else:
          self.response.out.write("[]") # empty array
      return
      
    # Processing for api/tracks and api/tracks/?genre=all
    if (self.request.get('genre') == 'all' or not self.request.get('genre')) and not \
       (self.request.get('location') or self.request.get('location_lat') or self.request.get('location_lon')): 
      tracks = models.Track.all().order('-created_at').fetch(limit, offset)
      if tracks:                           
        for track in tracks:
          add_to_track_array(track, track_array)
        return memcache_and_output_array(self, track_array)
      else:
        self.response.out.write("[]") # empty array
      return      

class TrackIDHandler(webapp.RequestHandler):
  """
    Fetching tracks. Returning json
  """
  def get(self, track_id=None): 

    memcached = memcache.get(self.request.path_qs, namespace='api_cache' )
    if memcached is not None and not utils.in_development_enviroment():
      return self.response.out.write(memcached)   
        
    if track_id:
      return fetch_track_by_id(self, track_id)
    else:
      error_response(self, 'no_track', 'You have provided no track id.')  
    return

class MaxTracksHandler(webapp.RequestHandler):
  """
    Fetch the biggest track_counter of the latest-updated locations. Returning json
  """
  def get(self):

    memcached = memcache.get(self.request.path_qs, namespace='api_cache' )
    if memcached is not None and not utils.in_development_enviroment():
      return self.response.out.write(memcached)

    # initialization
    locations_array = []
    genre = self.request.get('genre')   
    if self.request.get('limit'):
      limit = int(self.request.get('limit'))
    else:
      limit = settings.FRONTEND_LOCATIONS_LIMIT
    if self.request.get('offset'):
      offset = int(self.request.get('offset'))
    else:
      offset = 0

    # Processing latest locations for a certain genre api/locations/?genre={genre_name}
    if genre and genre != 'all':
      if genre not in utils.genres:
        error_response(self, 'unknown_genre', 'Sorry, but we do not know the genre %s.' % genre) 
        return
      location_genres = models.LocationGenreLastUpdate.all().order('-last_time_updated').filter('genre', genre).fetch(limit, offset)
      if location_genres:
        max_tracks = 0
        for location_genre in location_genres:
          if location_genre.track_counter > max_tracks:
            max_tracks = location_genre.track_counter
        return memcache_and_output_array(self, {'max_tracks': max_tracks}, (settings.MAX_TRACKS_CACHE_TIME-5))
      else:
        self.response.out.write("[]") # empty array
      return
    
    # Processing latest locations for api/locations
    if not genre or genre == 'all':
      locations = models.Location.all().order('-last_time_updated').fetch(limit, offset)
      if locations:
        max_tracks = 0
        for location in locations:
          if location.track_counter > max_tracks:
            max_tracks = location.track_counter
        return memcache_and_output_array(self, {'max_tracks': max_tracks}, (settings.MAX_TRACKS_CACHE_TIME-5))
      else:
        self.response.out.write("[]") # empty array
      return
                
class LocationsHandler(webapp.RequestHandler):
  """
    Fetching latest updated locations. Returning json
  """
  def get(self):
    
    memcached = memcache.get(self.request.path_qs, namespace='api_cache' )
    if memcached is not None and not utils.in_development_enviroment():
      return self.response.out.write(memcached)
    
    # initialization
    locations_array = []
    genre = self.request.get('genre')   
    if self.request.get('limit'):
      limit = int(self.request.get('limit'))
    else:
      limit = settings.FRONTEND_LOCATIONS_LIMIT
    if self.request.get('offset'):
      offset = int(self.request.get('offset'))
    else:
      offset = 0
    if self.request.get('location'):
      return fetch_location_by_id(self, self.request.get('location'))
    
    # Processing latest locations for a certain genre api/locations/?genre={genre_name}
    if genre and genre != 'all':
      if genre not in utils.genres:
        error_response(self, 'unknown_genre', 'Sorry, but we do not know the genre %s.' % genre) 
        return                                                                                   
      location_genres = models.LocationGenreLastUpdate.all().order('-last_time_updated').filter('genre', genre).fetch(limit, offset)
      if location_genres:
        for location_genre in location_genres:
          location_genre.location.track_counter = location_genre.track_counter              
          locations_array.append(create_location_dict(location_genre.location))
        return memcache_and_output_array(self, locations_array)
      else:
        self.response.out.write("[]") # empty array
      return
    
    # Processing latest locations for api/locations
    if not genre or genre == 'all':
      locations = models.Location.all().order('-last_time_updated').fetch(limit, offset)
      if locations:
        for location in locations:
          locations_array.append(create_location_dict(location))
        return memcache_and_output_array(self, locations_array)
      else:
        self.response.out.write("[]") # empty array
      return 
      

class LocationIDHandler(webapp.RequestHandler):
  """
    Fetching tracks. Returning json
  """
  def get(self, location_id=None):

    memcached = memcache.get(self.request.path_qs, namespace='api_cache' )
    if memcached is not None and not utils.in_development_enviroment():
      return self.response.out.write(memcached)
    
    if location_id:
      return fetch_location_by_id(self, location_id)
    else:
      error_response(self, 'no_location', 'You have provided no location id.')  
    return    
      
def main():
  application = webapp.WSGIApplication([(r'/api/tracks/([0-9]{1,64})', TrackIDHandler),
                                        ('/api/tracks.*', TracksHandler),
                                        ('/api/locations/maxtracks.*', MaxTracksHandler),
                                        (r'/api/locations/([0-9]{1,64})', LocationIDHandler),
                                        ('/api/locations.*', LocationsHandler)], debug=utils.in_development_enviroment())
  run_wsgi_app(application)

if __name__ == '__main__':
  main()