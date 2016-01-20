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
import os

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
        self.cache_path = self.conf.get('global', 'cache')
        # All sections except influxdb and global are cluster names. So get all
        # sections names minus those two.
        self.clusters = [ cluster for cluster in self.conf.sections()
                          if cluster not in ['influxdb', 'global'] ]

    def api(self, cluster):

        return self.conf.get(cluster, 'api')

    def login(self, cluster):

        return self.conf.get(cluster, 'login')

    def password(self, cluster):

        return self.conf.get(cluster, 'password')

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
            struct = json.load(cache_f)
            for cluster, data in struct.iteritems():
                self.cluster_caches[cluster] = \
                    ClusterCache(data['token'],
                                 data['auth_enabled'],
                                 data['auth_guest'])

    def write(self):

        struct = {}
        for cluster, cache in self.cluster_caches.iteritems():
            struct[cluster] = { 'token': cache.token,
                                'auth_enabled': cache.auth_enabled,
                                'auth_guest': cache.auth_guest }

        with open(self.path, 'w+') as cache_f:
            json.dump(struct, cache_f)

    def get(self, cluster):

        if self.cluster_caches is None:
            self.read()

        # The cluster cache does not exist yet. Create a new empty cache.
        if not self.cluster_caches.has_key(cluster):
            self.cluster_caches[cluster] = ClusterCache()

        return self.cluster_caches[cluster]

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

    def __init__(self, conf, cluster, cache):

        self.cluster = cluster
        self.base_url = conf.api(cluster)
        self.cache = cache
        self.auth_login = conf.login(cluster)
        self.auth_password = conf.password(cluster)

        if cache.empty is None:
            self.auth_token = None
            self.auth_enabled = None
            self.auth_guest = None
        else:
            self.auth_token = cache.token
            self.auth_enabled = cache.auth_enabled
            self.auth_guest = cache.auth_guest

    @property
    def auth_as_guest(self):

        return self.auth_login == 'guest'

    def check_auth(self):

        url = "{base}/authentication".format(base=self.base_url)
        try:
            resp = requests.get(url=url)
        except ConnectionError, err:
            # reformat the exception
            raise ConnectionError("connection error while trying to connect " \
                                  "to {url}: {error}" \
                                    .format(url=url, error=err))

        try:
            json_auth = json.loads(resp.text)
        except ValueError:
            # reformat the exception
            raise ValueError("not JSON data for GET {url}" \
                               .format(url=url))

        self.auth_enabled = json_auth['enabled']
        self.auth_guest = json_auth['guest']

    def login(self):

        url = "{base}/login".format(base=self.base_url)
        try:
            if self.auth_as_guest is True:
                payload = { "guest": True }
            else:
                payload = { "username": self.auth_login,
                            "password": self.auth_password }
            resp = requests.post(url=url, json=payload)
        except ConnectionError, err:
            # reformat the exception
            raise ConnectionError("connection error while trying to connect " \
                                  "to {url}: {error}" \
                                    .format(url=url, error=err))

        if resp.status_code != 200:
            raise Exception("login failed with {code} on API {api}" \
                               .format(code=resp.status_code,
                                       api=self.base_url))
        try:
            login = json.loads(resp.text)
        except ValueError:
            # reformat the exception
            raise ValueError("not JSON data for POST {url}" \
                               .format(url=url))

        self.auth_token = login['id_token']

    def ensure_auth(self):

        # If cache was able to give us a token, assume auth is enable, the
        # token is still valid and use it straightfully. If the token is not
        # valid according to slurm-web, the error will be handled then.
        if self.auth_token is not None:
            return

        # if auth_enabled is None, it means the cache was not able to tell us.
        # In this case, we have to check ourselves.
        if self.auth_enabled is None:
            self.check_auth()
            # update the cache with new data
            self.cache.auth_enabled = self.auth_enabled
            self.cache.auth_guest = self.auth_guest

        # if the auth is disable, go on with it.
        if self.auth_enabled is False:
            return

        # At this point, auth is enabled and we do not have token.

        # First check if the app is configured to log as guest and guest login
        # is enable.
        if self.auth_as_guest and self.auth_guest is False:
            raise Exception("unable to log as guest to {base}" \
                              .format(base=self.base_url))

        self.login()
        # update token in cache
        self.cache.token = self.auth_token

    def job_params(self, job, firsttime=True):
        """Request the Slurm REST API of the cluster to get Job params. Raises
           IndexError if job is not found or ValueError if not well formatted
           JSON data sent by the API.
        """

        self.ensure_auth()

        url = "{base}/job/{job}" \
                  .format(base=self.base_url,
                          job=job)
        try:
            if self.auth_enabled is True:
                payload = { 'token': self.auth_token }
                resp = requests.post(url=url, json=payload)
            else:
                resp = requests.post(url=url)
        except ConnectionError, err:
            # reformat the exception
            raise ValueError("connection error while trying to connect to " \
                             "{url}: {error}".format(url=url, error=err))

        if resp.status_code == 404:
            raise IndexError("job ID {jobid} not found in API {api}" \
                               .format(jobid=job, api=self.base_url))

        if resp.status_code == 403:
            if firsttime:
                # We probably get this error because of invalidated token.
                # Invalidate cache, trigger check_auth() and call this method
                # again.
                self.auth_token = None
                self.auth_enabled = None
                self.cache.invalidate()
                return self.job_params(job, firsttime=False)
            else:
                # We have already tried twice. This means the app is not able
                # to auth on slurm-web API with current params. Just throw the
                # error and give-up here.
                raise Exception("get 403/forbidden from {url} with new token" \
                                  .format(url=self.base_url))
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
     cache = Cache(conf.cache_path)
     cluster_cache = cache.get(cluster)
     slurm_api = SlurmAPI(conf, cluster, cluster_cache)

     job = JobParams(jobid)

     try:
         job.request_params(slurm_api)
     except IndexError, err:
         # IndexError here means the job is unknown according to Slurm API.
         # Return 404 with error message
         abort(404, { 'error': str(err) })
     except (ValueError, ConnectionError, Exception) as err:
         # ValueError means the Slurm API responded something that was not
         # JSON formatted. ConnectionError means there was a problem while
         # connection to the slurm API. Return 500 with error message.
         abort(500, { 'error': str(err) })

     # Write the cache at this point since it will not be modified then
     cache.write()

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
