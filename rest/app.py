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


from flask import Flask, jsonify, abort
from requests.exceptions import ConnectionError

import logging
from logging.handlers import TimedRotatingFileHandler
from logging import Formatter

from jobmetrics.Conf import Conf, periods
from jobmetrics.Cache import Cache
from jobmetrics.SlurmAPI import SlurmAPI
from jobmetrics.MetricsDB import MetricsDB
from jobmetrics.JobParams import JobParams
from jobmetrics.JobData import JobData
from jobmetrics.Profiler import Profiler

app = Flask('jobmetrics')
# By default flask redirects "metrics/CLUSTER/JOB/1h" to
# "metrics/CLUSTER/JOB" since 1h is the default. This is nice on
# a browser but the JS client doesn't like it
app.url_map.redirect_defaults = False


@app.errorhandler(500)
def internal_error(error):
    if not hasattr(error, 'description'):
        error.description = {'error': 'unknown internal error'}
    app.logger.error("error 500: %s", error.description['error'])
    app.logger.exception(error)
    response = jsonify(error.description)
    response.status_code = 500
    return response


@app.errorhandler(404)
def page_not_found(error):
    app.logger.error("error 404: %s", error.description['error'])
    response = jsonify(error.description)
    response.status_code = 404
    return response


def init_logger(conf):

    log_h = TimedRotatingFileHandler(conf.log_path,
                                     when='D',
                                     interval=1,
                                     backupCount=10)
    if conf.debug:
        log_h.setLevel(logging.DEBUG)
    else:
        log_h.setLevel(logging.INFO)
    log_h.setFormatter(Formatter(
        '%(asctime)s %(filename)s:%(lineno)d %(levelname)s: %(message)s'))

    # Remove all other handlers and disable propagation to ancestor logger in
    # order to avoid polluting HTTP server error log with app specific logs.
    app.logger.propagate = False
    app.logger.handlers = []
    app.logger.addHandler(log_h)
    if conf.debug:
        app.logger.setLevel(logging.DEBUG)
    else:
        app.logger.setLevel(logging.INFO)


@app.route('/metrics/<cluster>/<int:jobid>', defaults={'period': '1h'})
@app.route('/metrics/<cluster>/<int:jobid>/<period>')
def metrics(cluster, jobid, period):

    conf = Conf()

    init_logger(conf)

    cache = Cache(conf.cache_path)
    cluster_cache = cache.get(cluster)
    slurm_api = SlurmAPI(conf, cluster, cluster_cache)
    profiler = Profiler()
    job = JobParams(jobid)

    app.logger.info("GET cluster %s jobid %d" % (cluster, jobid))

    try:
        job.request_params(slurm_api)
    except IndexError as err:
        # IndexError here means the job is unknown according to Slurm API.
        # Return 404 with error message
        abort(404, {'error': str(err)})
    except (ValueError, ConnectionError, Exception) as err:
        # ValueError means the Slurm API responded something that was not
        # JSON formatted. ConnectionError means there was a problem while
        # connection to the slurm API. Return 500 with error message.
        abort(500, {'error': err.message})

    # Write the cache at this point since it will not be modified then
    cache.write()

    # Check the period given in parameter is valid. If not, return 500.
    if period not in periods.keys():
        abort(500, {'error': "period %s is not valid" % (period)})

    try:
        db = MetricsDB(conf)
        job_data = JobData(cluster, job, period)
        job_data.request(db)
        resp = {}
        resp['data'] = job_data.dump()
        resp['debug'] = profiler.dump()
        return jsonify(resp)
    except Exception as err:
        app.logger.exception(err)
        abort(500, {'error': str(err)})

if __name__ == '__main__':
    app.run(debug=True)
