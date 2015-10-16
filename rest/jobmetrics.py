#!flask/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015 EDF SA
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

import ConfigParser
from flask import Flask, jsonify, abort
from ClusterShell.NodeSet import NodeSet
import requests
import json

app = Flask(__name__)

# valid periods with their associated interval group time
periods = { '1h': '10s',
            '6h': '30s',
            '24h': '120s' }

class Conf(object):

    def __init__(self, fpath='/etc/jobmetrics/jobmetrics.conf'):
        self.conf = ConfigParser.RawConfigParser()
        self.conf.read(fpath)
        self.influxdb_server = self.conf.get('influxdb', 'server')
        self.influxdb_db = self.conf.get('influxdb', 'db')
        self.clusters = self.conf.sections().remove('influxdb')

    def slurm_api(self, cluster):
        return self.conf.get(cluster, 'slurm-api')

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

        metrics_s = "\"" + "\", \"".join(metrics) + "\""
        req = "select mean(value) from {metrics} " \
              "where time > now() - {period} " \
              "and cluster = '{cluster}' " \
              "and job = 'job_{job}' " \
              "group by time({time_group}), node fill(0)" \
                .format(metrics=metrics_s,
                        period=period,
                        cluster=cluster,
                        job=job,
                        time_group=time_group)

        payload = {'db': self.db, 'q': req, 'epoch': 'ms'}
        resp = requests.get(url=self.url, params=payload)
        if resp.status_code == 404:
            raise LookupError("metrics not found for job {job} on cluster " \
                              "{cluster}".format(job=job, cluster=cluster))
        data = json.loads(resp.text)

        # data is a dict with 'results' key that is itself a list of dict with
        # 'series' key that is as well a list of dict, one dict per node/node
        # association. Each dict has it own list of values. We have to compute the
        # sum the values for all nodes at every timestampsi, for each metric.
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
        series = data['results'][0]['series']

        results = {}
        nodeset = NodeSet()

        for serie in series:
            metric = serie['name']
            node = serie['tags']['node'].encode('utf-8')

            if node not in nodeset:
                nodeset.update(node)

            for pair in serie['values']:
                timestamp = str(pair[0])
                value = pair[1]
                if not results.has_key(timestamp):
                    results[timestamp] = list()
                    for xidx in range(len(metrics)):
                        if xidx == metrics.index(metric):
                            results[timestamp].append(value)
                        else:
                            results[timestamp].append(0)
                else:
                    results[timestamp][metrics.index(metric)] += value

        return (results, nodeset)

class SlurmAPI(object):

    def __init__(self, conf, cluster):

        self.base_url = conf.slurm_api(cluster)

    def job_state(self, job):
        """Request the Slurm REST API of the cluster to check if the job actually
           exists. Return NOTFOUND if not.
        """

        url = "{base}/job/{job}" \
                  .format(base=self.base_url,
                          job=job)
        resp = requests.get(url=url)
        if resp.status_code == 404:
            state = 'NOTFOUND'
        else:
            data = json.loads(resp.text)
            state = data['job_state']

        return state

class JobData(object):

    def __init__(self, cluster, job, period):

        self.cluster = cluster
        self.job = job
        self.period = period
        self.nodeset = None
        self.metrics = None

    def request(self, db):

        (self.metrics, self.nodeset) = db.get_metrics_results(
                                           self.cluster,
                                           self.job,
                                           ['cpus',
                                            'cpu-user',
                                            'cpu-system',
                                            'memory-pss'],
                                           self.period)
        self.stack_cpu_idle()

    def stack_cpu_idle(self):
        """Compute the sum of cpu usages in metrics dict in parameters to stack
           the idle cpu time and append in into the dict.
        """

        for timestamp, values in self.metrics.iteritems():
            values.insert(3, values[0]*100 - values[1] - values[2])

    def jsonify(self):

        datahash = {}
        datahash['data'] = self.metrics
        datahash['job'] = {}
        datahash['job']['nodeset'] = str(self.nodeset)
        return jsonify(datahash)

@app.route('/metrics/<cluster>/<int:job>', defaults={'period': '1h'})
@app.route('/metrics/<cluster>/<int:job>/<period>')
def metrics(cluster, job, period):

     conf = Conf()
     slurm_api = SlurmAPI(conf, cluster)
     job_state = slurm_api.job_state(job)

     if period not in periods.keys():
         abort(500)

     if (job_state == 'NOTFOUND'):
         # No way to get job time boundaries as of now... So get nothing
         # more clever to do here.
         abort(404)
     else:
         try:
             db = MetricsDB(conf)
             job_data = JobData(cluster, job, period)
             job_data.request(db)
             return job_data.jsonify()
         except Exception, e:
             print("Error: " + str(e))
             abort(500)

if __name__ == '__main__':
    app.run(debug=True)
