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

from jobmetrics.Conf import Conf, periods
from jobmetrics.Cache import Cache
from jobmetrics.SlurmAPI import SlurmAPI
from jobmetrics.MetricsDB import MetricsDB
from jobmetrics.JobParams import JobParams
from jobmetrics.JobData import JobData

app = Flask(__name__)

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
