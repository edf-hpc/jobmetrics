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
import requests
import json

CONF = '/etc/jobmetrics/jobmetrics.conf'
app = Flask(__name__)
conf = None

# valid periods with their associated interval group time
periods = { '1h': '10s',
            '6h': '30s',
            '24h': '120s' }

def get_job_state(cluster, job):
    """Request the Slurm REST API of the cluster to check if the job actually
       exists. Return NOTFOUND if not.
    """

    url = "{api}/job/{job}" \
              .format(api=conf.get(cluster, 'slurm-api'),
                      job=job)
    resp = requests.get(url=url)
    if resp.status_code == 404:
        state = 'NOTFOUND'
    else:
        data = json.loads(resp.text)
        state = data['job_state']

    return state

def stack_cpu_idle(metrics):
    """Compute the sum of cpu usages in metrics dict in parameters to stack
       the idle cpu time and append in into the dict.
    """

    for timestamp, values in metrics.iteritems():
        values.append(values[0]*100 - values[1] - values[2])

def get_metric_results(cluster, job, metric, period, group=''):
    """Get the metrics of the job on the cluster for the period in parameters.

       It sends an HTTP request to InfluxDB service to download the metric
       values in JSON format and returns a list.

       The group parameter is concatenated in the request to add optional
       additional group by clause. This is typically used for nodes in
       get_job_node_metrics() function.
    """

    time_group = periods[period]

    url = "{influxdb}/query".format(influxdb=conf.get('influxdb', 'server'))
    req = "select mean(value) from \"{metric}\" " \
          "where time > now() - {period} " \
          "and cluster = '{cluster}' " \
          "and job = 'job_{job}' " \
          "group by time({time_group}){group} fill(0)" \
            .format(metric=metric,
                    period=period,
                    cluster=cluster,
                    job=job,
                    time_group=time_group,
                    group=group)
    db = conf.get('influxdb', 'db')

    payload = {'db': db, 'q': req, 'epoch': 'ms'}
    resp = requests.get(url=url, params=payload)
    if resp.status_code == 404:
        raise LookupError("metrics not found for job {job} on cluster " \
                          "{cluster}".format(job=job, cluster=cluster))
    data = json.loads(resp.text)
    results = data['results'][0]['series']

    return results

def get_job_node_metrics(metrics, cluster, job, metric, period):
    """Get the node related metric for the cluster and the job for the period
       in parameter. It compute the sum of all metric node series to get only
       one global serie for all nodes. It appends the result into the metrics
       dict in parameter.
    """

    results = get_metric_results(cluster, job, metric, period, ', node')

    # Result is a list of dict, one dict per node. Each dict has it own list of
    # values. We have to compute the sum the values for all nodes at every
    # timestamps.
    #
    # Ex:
    # [
    #   {u'values': [[1441614640000, 0],
    #                [1441614650000, 3188736.0],
    #                  ...
    #                [1441614700000, 3188736.0]],
    #    u'name': u'memory-pss',
    #    u'columns': [u'time', u'mean'],
    #    u'tags': {u'node': u'cn1'}},
    #   {u'values': [[1441614640000, 0],
    #                [1441614650000, 3115008.0],
    #                  ...
    #                [1441614700000, 3115008.0]],
    #   u'name': u'memory-pss',
    #   u'columns': [u'time', u'mean'],
    #   u'tags': {u'node': u'cn2'}},
    #  {u'values': [[1441614640000, 0],
    #               [1441614650000, 3214336.0],
    #                  ...
    #               [1441614700000, 3214336.0]],
    #   u'name': u'memory-pss',
    #   u'columns': [u'time', u'mean'],
    #   u'tags': {u'node': u'cn3'}}
    # ]

    value_idx = 0
    for value in results[0]['values']:
        # value in an array with 2 items:
        #   - a timestamp
        #   - the metric value at this timestamp

        total = 0
        for node_serie in results:
            total += node_serie['values'][value_idx][1]
        metrics[value[0]].append(total)
        value_idx += 1

def get_job_metrics(metrics, cluster, job, metric, period):
    """Get the job metric for the job on the cluster for the period in
       parameter. Append the result into the metrics dict in parameter.
    """

    results = get_metric_results(cluster, job, metric, period)
    for value in results[0]['values']:
        # value in an array with 2 items:
        #   - a timestamp
        #   - the metric value at this timestamp
        metrics[value[0]] = [ value[1] ]

def read_conf():
    """Read/parse configuration file and set global conf variable."""

    global conf
    conf = ConfigParser.RawConfigParser()
    conf.read(CONF)

@app.route('/metrics/<cluster>/<int:job>', defaults={'period': '1h'})
@app.route('/metrics/<cluster>/<int:job>/<period>')
def metrics(cluster, job, period):

     read_conf()
     job_state = get_job_state(cluster, job)

     if period not in periods.keys():
         abort(500)

     if (job_state == 'NOTFOUND'):
         # No way to get job time boundaries as of now... So get nothing
         # more clever to do here.
         abort(404)
     else:
         try:
             metrics = {}
             get_job_metrics(metrics, cluster, job, 'cpus', period)
             get_job_node_metrics(metrics, cluster, job, 'cpu-user', period)
             get_job_node_metrics(metrics, cluster, job, 'cpu-system', period)
             stack_cpu_idle(metrics)
             get_job_node_metrics(metrics, cluster, job, 'memory-pss', period)
             return jsonify(metrics)
         except Exception, e:
             print(e)
             abort(500)

if __name__ == '__main__':
    app.run(debug=True)
