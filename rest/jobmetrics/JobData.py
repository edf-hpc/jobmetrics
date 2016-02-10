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

from jobmetrics.Profiler import Profiler


class JobData(object):

    def __init__(self, cluster, job, period):

        self.cluster = cluster
        self.job = job
        self.period = period
        self.nodeset = None
        self.metrics = None

    def request(self, db):

        (self.metrics, self.nodeset) = \
            db.get_metrics_results(self.cluster,
                                   self.job,
                                   ['cpus',
                                    'cpu-user',
                                    'cpu-system',
                                    'memory-pss'],
                                   self.period)
        self.stack_cpu_idle()
        profiler = Profiler()
        profiler.meta('producers', str(self.nodeset))
        profiler.meta('nodes', str(self.job.nodeset))
        profiler.meta('mutes', str(self.job.nodeset - self.nodeset))

    def stack_cpu_idle(self):
        """Compute the sum of cpu usages in metrics dict in parameters to stack
           the idle cpu time and append in into the dict.
        """

        for timestamp, values in self.metrics.iteritems():
            values.insert(3, values[0]*100 - values[1] - values[2])

    def dump(self):
        return self.metrics
        return datahash
