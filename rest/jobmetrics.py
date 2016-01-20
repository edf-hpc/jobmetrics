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
from requests.exceptions import ConnectionError
import json

app = Flask(__name__)

# valid periods with their associated interval group time
periods = { '1h': '10s',
            '6h': '30s',
            '24h': '120s' }

@app.errorhandler(500)
def internal_error(error):
    if not hasattr(error, 'description'):
        error.description = { 'error' : 'unknown internal error'}
    response = jsonify(error.description)
    response.status_code = 500
    return response

@app.errorhandler(404)
def page_not_found(error):
    response = jsonify(error.description)
    response.status_code = 404
    return response

class Conf(object):

    def __init__(self, fpath='/etc/jobmetrics/jobmetrics.conf'):
        self.conf = ConfigParser.RawConfigParser()
        self.conf.read(fpath)
        self.influxdb_server = self.conf.get('influxdb', 'server')
        self.influxdb_db = self.conf.get('influxdb', 'db')
        # All sections except influxdb are cluster names. So get all sections
        # names minus influxdb.
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
                        job=job.jobid,
                        time_group=time_group)

        payload = {'db': self.db, 'q': req, 'epoch': 'ms'}
        resp = requests.get(url=self.url, params=payload)
        if resp.status_code == 404:
            raise LookupError("metrics not found for job {job} on cluster " \
                              "{cluster}".format(job=job.jobid, cluster=cluster))
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
                    # The cpus/nodes metrics can be produced by several batch
                    # servers and thus returned multiple times by InfluxDB
                    # server in the result of the request. We must take care to
                    # not add the multiple results of this metric here!
                    if metric in ['cpus', 'nodes']:
                        results[timestamp][metrics.index(metric)] = value
                    else:
                        results[timestamp][metrics.index(metric)] += value

        return (results, nodeset)

class JobParams(object):

    def __init__(self, jobid):

       self.jobid = jobid
       self.state = None
       self.nodeset = None

    def request_params(self, api):
       params = api.job_params(self.jobid)
       self.state = params['job_state']
       self.nodeset = NodeSet(params['nodes'].encode('utf-8'))

class SlurmAPI(object):

    def __init__(self, conf, cluster):

        self.base_url = conf.slurm_api(cluster)

    def job_params(self, job):
        """Request the Slurm REST API of the cluster to get Job params. Raises
           IndexError if job is not found or ValueError if not well formatted
           JSON data sent by the API.
        """

        url = "{base}/job/{job}" \
                  .format(base=self.base_url,
                          job=job)
        try:
            resp = requests.get(url=url)
        except ConnectionError, err:
            # reformat the exception
            raise ValueError("connection error while trying to connect to " \
                             "{url}: {error}".format(url=url, error=err))

        if resp.status_code == 404:
            raise IndexError("job ID {jobid} not found in API {api}" \
                               .format(jobid=job, api=self.base_url))
        try:
            json_job = json.loads(resp.text)
        except ValueError:
            # reformat the exception
            raise ValueError("not JSON data for GET {url}" \
                               .format(url=url))
        return json_job

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
        datahash['job']['producers'] = str(self.nodeset)
        datahash['job']['nodes'] = str(self.job.nodeset)
        datahash['job']['mutes'] = str(self.job.nodeset - self.nodeset)
        return jsonify(datahash)

@app.route('/metrics/<cluster>/<int:jobid>', defaults={'period': '1h'})
@app.route('/metrics/<cluster>/<int:jobid>/<period>')
def metrics(cluster, jobid, period):

     conf = Conf()
     slurm_api = SlurmAPI(conf, cluster)
     job = JobParams(jobid)

     try:
         job.request_params(slurm_api)
     except IndexError, err:
         # IndexError here means the job is unknown according to Slurm API.
         # Return 404 with error message
         abort(404, { 'error': str(err) })
     except (ValueError, ConnectionError) as err:
         # ValueError means the Slurm API responded something that was not
         # JSON formatted. ConnectionError means there was a problem while
         # connection to the slurm API. Return 500 with error message.
         abort(500, { 'error': str(err) })

     # Check the period given in parameter is valid. If not, return 500.
     if period not in periods.keys():
         abort(500, { 'error': "period %s is not valid" % (period) })

     try:
         db = MetricsDB(conf)
         job_data = JobData(cluster, job, period)
         job_data.request(db)
         return job_data.jsonify()
     except Exception, err:
         abort(500, { 'error': str(err) })

if __name__ == '__main__':
    app.run(debug=True)
