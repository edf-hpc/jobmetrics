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

class ClusterCache(object):

    def __init__(self, token=None, auth_enabled=None, auth_guest=None):

        self.token = token
        self.auth_enabled = auth_enabled
        self.auth_guest = auth_guest

    @property
    def empty(self):
        return self.token is None and \
               self.auth_enabled is None and \
               self.auth_guest is None

    def invalidate(self):

        self.token = None
        self.auth_enabled = None
        self.auth_guest = None
