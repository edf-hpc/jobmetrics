#!flask/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2016 EDF SA
#
# This file is part of jobmetrics.
#
# jobmetrics is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# jobmetrics is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with jobmetrics.  If not, see <http://www.gnu.org/licenses/>.

"""The Profiler class is a Singleton object (using the so-called metaclass)
   used across all Jobmetrics backend application to manage a set of internal
   profiling timers and metadata."""

import time
import thread


class Singleton(type):

    """ Singleton thread-safe metaclass """

    __instances = {}
    __lockObj = thread.allocate_lock()  # lock object

    def __call__(mcs, *args, **kwargs):
        mcs.__lockObj.acquire()
        try:
            if mcs not in mcs.__instances:
                mcs.__instances[mcs] = super(Singleton, mcs) \
                    .__call__(*args, **kwargs)
        finally:
            #  Exit from critical section whatever happens
            mcs.__lockObj.release()

        return mcs.__instances[mcs]

    def initialized(mcs):

        return mcs in mcs.__instances


class Profiler(object):

    __metaclass__ = Singleton

    def __init__(self):

        self.metadata = {}
        self.timers = {}
        self.starts = {}

    def meta(self, key, value):

        self.metadata[key] = value

    def start(self, timer):

        if timer not in self.timers:
            self.starts[timer] = time.clock()
            self.timers[timer] = float(-1)

    def stop(self, timer):

        if timer not in self.timers:
            return  # ignore silently

        self.timers[timer] = time.clock() - self.starts[timer]

    def dump(self):

        return {'timers': self.timers,
                'metadata': self.metadata}
