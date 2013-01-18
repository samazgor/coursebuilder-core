# Copyright 2012 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS-IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Core data model classes."""

__author__ = 'Pavel Simakov (psimakov@google.com)'


import os
from config import ConfigProperty
from counters import PerfCounter
from entities import BaseEntity
from google.appengine.api import memcache
from google.appengine.api import users
from google.appengine.ext import db


# Whether we are running in the production environment.
PRODUCTION_MODE = not os.environ.get(
    'SERVER_SOFTWARE', 'Development').startswith('Development')

# The default amount of time to cache the items for in memcache.
DEFAULT_CACHE_TTL_SECS = 60 * 60

# Whether memcache caching is enabled.
GCB_IS_MEMCACHE_ENABLED = ConfigProperty(
    'gcb_is_memcache_enabled', bool, (
        'A flag that controls whether memcache is enabled. By default, '
        'it\'s "off" for development and "on" for production servers.'),
    PRODUCTION_MODE)

# performance counters
CACHE_PUT = PerfCounter(
    'gcb-models-cache-put',
    'A number of times an object was put into memcache.')
CACHE_HIT = PerfCounter(
    'gcb-models-cache-hit',
    'A number of times an object was found in memcache.')
CACHE_MISS = PerfCounter(
    'gcb-models-cache-miss',
    'A number of times an object was not found in memcache.')
CACHE_DELETE = PerfCounter(
    'gcb-models-cache-delete',
    'A number of times an object was deleted from memcache.')


class MemcacheManager(object):
    """Class that consolidates all memcache operations."""

    @classmethod
    def enabled(cls):
        return GCB_IS_MEMCACHE_ENABLED.value

    @classmethod
    def get(cls, key):
        """Gets an item from memcache if memcache is enabled."""
        if MemcacheManager.enabled():
            value = memcache.get(key)
            if value:
                CACHE_HIT.inc()
            else:
                CACHE_MISS.inc()
            return value
        else:
            return None

    @classmethod
    def set(cls, key, value):
        """Sets an item in memcache if memcache is enabled."""
        if MemcacheManager.enabled():
            CACHE_PUT.inc()
            memcache.set(key, value, DEFAULT_CACHE_TTL_SECS)

    @classmethod
    def delete(cls, key):
        """Deletes an item from memcache if memcache is enabled."""
        if MemcacheManager.enabled():
            CACHE_DELETE.inc()
            memcache.delete(key)


class Student(BaseEntity):
    """Student profile."""
    enrolled_date = db.DateTimeProperty(auto_now_add=True, indexed=False)
    name = db.StringProperty(indexed=False)
    is_enrolled = db.BooleanProperty()

    # Each of the following is a string representation of a JSON dict.
    answers = db.TextProperty()
    scores = db.TextProperty()

    def put(self):
        """Do the normal put() and also add the object to memcache."""
        result = super(Student, self).put()
        MemcacheManager.set(self.key().name(), self)
        return result

    def delete(self):
        """Do the normal delete() and also remove the object from memcache."""
        super(Student, self).delete()
        MemcacheManager.delete(self.key().name())

    @classmethod
    def get_by_email(cls, email):
        return Student.get_by_key_name(email.encode('utf8'))

    @classmethod
    def get_enrolled_student_by_email(cls, email):
        student = MemcacheManager.get(email)
        if not student:
            student = Student.get_by_email(email)
            MemcacheManager.set(email, student)
        if student and student.is_enrolled:
            return student
        else:
            return None

    @classmethod
    def rename_current(cls, new_name):
        """Gives student a new name."""
        user = users.get_current_user()
        if not user:
            raise Exception('No current user.')
        if new_name:
            student = Student.get_by_email(user.email())
            student.name = new_name
            student.put()

    @classmethod
    def set_enrollment_status_for_current(cls, is_enrolled):
        """Changes student enrollment status."""
        user = users.get_current_user()
        if not user:
            raise Exception('No current user.')
        student = Student.get_by_email(user.email())
        student.is_enrolled = is_enrolled
        student.put()
