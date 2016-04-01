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

import json
import os

from jobmetrics.ClusterCache import ClusterCache


class Cache(object):

    def __init__(self, path):

        self.path = path
        self.cluster_caches = None

    def read(self):

        # ensure dict is empty
        self.cluster_caches = {}

        if not os.path.exists(self.path):
            return

        with open(self.path, 'r') as cache_f:
            try:
                struct = json.load(cache_f)
            except ValueError:
                # File exists but does not contain json data (probably empty).
                # In this case, return None so that cluster_caches dict stays
                # empty. It will be filled then with new data.
                return None
            for cluster, data in struct.iteritems():
                self.cluster_caches[cluster] = \
                    ClusterCache(data['token'],
                                 data['auth_enabled'],
                                 data['auth_guest'])

    def write(self):

        struct = {}
        for cluster, cache in self.cluster_caches.iteritems():
            struct[cluster] = {'token': cache.token,
                               'auth_enabled': cache.auth_enabled,
                               'auth_guest': cache.auth_guest}

        with open(self.path, 'w+') as cache_f:
            json.dump(struct, cache_f)

    def get(self, cluster):

        if self.cluster_caches is None:
            self.read()

        # The cluster cache does not exist yet. Create a new empty cache.
        if cluster not in self.cluster_caches:
            self.cluster_caches[cluster] = ClusterCache()

        return self.cluster_caches[cluster]
