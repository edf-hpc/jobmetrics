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

from ClusterShell.NodeSet import NodeSet


class JobParams(object):

    def __init__(self, jobid):

        self.jobid = jobid
        self.state = None
        self.nodeset = None

    def request_params(self, api):

        params = api.job_params(self.jobid)
        self.state = params['job_state']
        self.nodeset = NodeSet(params['nodes'].encode('utf-8'))
