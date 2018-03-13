#!flask/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2018 EDF SA
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

import logging
logger = logging.getLogger(__name__)

import requests
import json
from ClusterShell.NodeSet import NodeSet

from jobmetrics.Conf import periods
from jobmetrics.Profiler import Profiler


class MetricsDB(object):

    def __init__(self, conf):

        self.base_url = conf.influxdb_server
        self.db = conf.influxdb_db
        self.url = "{base}/query".format(base=self.base_url)

    def get_metrics_results(self, cluster, job, metrics, period):
        """Get the metrics of the job on the cluster for the period in parameters.

           It sends an HTTP request to InfluxDB service to download the metric
           values in JSON format and returns a list.
        """

        time_group = periods[period]

        profiler = Profiler()

        metrics_s = "\"" + "\", \"".join(metrics) + "\""
        req = "select mean(value) from {metrics} " \
              "where time > now() - {period} " \
              "and cluster = '{cluster}' " \
              "and job = 'job_{job}' " \
              "group by time({time_group}), node fill(0)" \
              .format(metrics=metrics_s,
                      period=period,
                      cluster=cluster,
                      job=job.jobid,
                      time_group=time_group)

        profiler.meta('metrics_req', req)

        payload = {'db': self.db, 'q': req, 'epoch': 'ms'}

        profiler.start('metrics_req')
        resp = requests.get(url=self.url, params=payload)
        profiler.stop('metrics_req')
        if resp.status_code == 404:
            raise LookupError("metrics not found for job {job} on cluster "
                              "{cluster}"
                              .format(job=job.jobid,
                                      cluster=cluster))

        profiler.start('metrics_proc')

        json_data = json.loads(resp.text)

        # data is a dict with 'results' key that is itself a list of dict with
        # 'series' key that is as well a list of dict, one dict per node/node
        # association. Each dict has it own list of values. We have to compute
        # the sum the values for all nodes at every timestampsi, for each
        # metric.
        #
        # Ex:
        #
        # { "results": [
        #   { "series": [
        #     { "name": "cpu-system",
        #       "tags": {"node":"cn1"},
        #       "columns": ["time","mean"],
        #       "values": [
        #         ["2015-10-16T11:37:20Z",0],
        #         ...
        #         ["2015-10-16T12:37:10Z",0],
        #         ["2015-10-16T12:37:20Z",0]
        #       ]
        #     },
        #     { "name": "cpu-system",
        #       "tags": {"node":"cn2"},
        #       "columns": ["time","mean"],
        #       "values": [
        #         ["2015-10-16T11:37:20Z",0],
        #         ["2015-10-16T11:37:30Z",0],
        #         ...
        #         ["2015-10-16T12:37:10Z",0],
        #        ["2015-10-16T12:37:20Z",0]
        #       ]
        #     },
        #
        #     ( ... then cpu-system for cn3 ...)
        #
        #     { "name": "cpu-user",
        #       "tags": {"node":"cn1"},
        #       "columns": ["time","mean"],
        #       "values": [
        #         ["2015-10-16T11:37:20Z",0],
        #         ["2015-10-16T11:37:30Z",0],
        #         ...
        #         ["2015-10-16T12:37:10Z",0],
        #         ["2015-10-16T12:37:20Z",0]
        #       ]
        #     },
        #
        #     ( ... then cpu-user for cn[2-3] ...)
        #
        #     { "name": "cpus",
        #       "tags": {"node":"admin"},
        #       "columns": ["time","mean"],
        #       "values": [
        #         ["2015-10-16T11:37:20Z",0],
        #         ["2015-10-16T11:37:30Z",0],
        #         ...
        #         ["2015-10-16T12:37:10Z",6],
        #         ["2015-10-16T12:37:20Z",0]
        #       ]
        #     },
        #     { "name": "memory-pss",
        #       "tags": {"node":"cn1"},
        #       "columns": ["time","mean"],
        #       "values": [
        #         ["2015-10-16T11:37:20Z",0],
        #         ["2015-10-16T11:37:30Z",0],
        #         ...
        #         ["2015-10-16T12:37:10Z",0],
        #         ["2015-10-16T12:37:20Z",0]
        #       ]
        #     },
        #
        #     ( ... then memory-pss for cn[2-3] ...)
        #
        #   ]}
        # ]}

        results = {}
        nodeset = NodeSet()
        for result in json_data['results']:
            if 'series' in result:
                series = result['series']
            else:
                logger.warn("No series in one result for query: %s", req)
                series = {}

            for serie in series:
                metric = serie['name']
                node = serie['tags']['node'].encode('utf-8')

                if node not in nodeset:
                    nodeset.update(node)

                for pair in serie['values']:
                    timestamp = str(pair[0])
                    value = pair[1]
                    if timestamp not in results:
                        # init all values for timestamp to 0
                        results[timestamp] = [0]*len(metrics)
                    # The cpus/nodes metrics can be produced by several
                    # batch servers and thus returned multiple times by
                    # InfluxDB server in the result of the request. We
                    # must take care to not add the multiple results of
                    # this metric here!
                    if metric in ['cpus', 'nodes']:
                        results[timestamp][metrics.index(metric)] = value
                    else:
                        results[timestamp][metrics.index(metric)] += value

        profiler.stop('metrics_proc')
        return (results, nodeset)
