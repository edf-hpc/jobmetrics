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

import logging
logger = logging.getLogger(__name__)
import json
import requests
from requests.exceptions import ConnectionError
from jobmetrics.Profiler import Profiler


class SlurmAPI(object):

    def __init__(self, conf, cluster, cache):

        self.cluster = cluster
        self.base_url = conf.api(cluster)
        self.cache = cache
        self.auth_login = conf.login(cluster)
        self.auth_password = conf.password(cluster)
        self.auth_enabled = conf.auth_enabled(cluster)
        if conf.tls_verify:
            self.ca_filepath = conf.ca_filepath
        else:
            self.ca_filepath = False

        logger.debug("Cluster %s (ca_filepath: %s)",
                     self.cluster, self.ca_filepath)

        if cache.empty is None:
            self.auth_token = None
        else:
            self.auth_token = cache.token

    @property
    def auth_as_guest(self):

        return self.auth_login == 'guest'

    @property
    def auth_as_trusted_source(self):

        return self.auth_login == 'trusted_source'

    def login(self):

        logger.info("login to %s for new token", self.base_url)

        url = "{base}/login".format(base=self.base_url)

        try:
            if self.auth_as_guest is True:
                payload = {"guest": True}
            elif self.auth_as_trusted_source is True:
                payload = {"trusted_source": True}
            else:
                logger.debug("Trying to login with username: %s",
                             self.auth_login)
                if self.auth_password is None:
                    logger.warn("No password provided")
                payload = {"login": self.auth_login,
                           "password": self.auth_password}
            resp = requests.post(url=url,
                                 json=payload,
                                 verify=self.ca_filepath)
        except ConnectionError as err:
            logger.warn("Connection Error args: %s", err.args)
            # reformat the exception
            raise ConnectionError("connection error while trying to connect "
                                  "to {url}: {error}"
                                  .format(url=url, error=err.strerror))

        if resp.status_code != 200:
            raise Exception("login failed with {code} on API {api}"
                            .format(code=resp.status_code,
                                    api=self.base_url))
        try:
            data = json.loads(resp.text)
        except ValueError:
            # reformat the exception
            raise ValueError("not JSON data for POST {url}"
                             .format(url=url))

        self.auth_token = data['id_token']

    def ensure_auth(self):

        # If cache was able to give us a token, assume auth is enable, the
        # token is still valid and use it straightfully. If the token is not
        # valid according to slurm-web, the error will be handled then.
        if self.auth_token is not None:
            return

        # if the auth is disable, go on with it.
        if self.auth_enabled is False:
            return

        # At this point, auth is enabled and we do not have token.
        self.login()
        # update token in cache
        self.cache.token = self.auth_token

    def job_params(self, job, firsttime=True):
        """Request the Slurm REST API of the cluster to get Job params. Raises
           IndexError if job is not found or ValueError if not well formatted
           JSON data sent by the API.
        """

        profiler = Profiler()
        profiler.start('slurm_auth')
        self.ensure_auth()
        profiler.stop('slurm_auth')

        url = "{base}/job/{job}".format(base=self.base_url, job=job)

        try:
            profiler.start('slurm_req')
            if self.auth_enabled is True:
                headers = {'Authorization': "Bearer %s" % self.auth_token}
                resp = requests.get(url=url,
                                    headers=headers,
                                    verify=self.ca_filepath)
            else:
                resp = requests.get(url=url, verify=self.ca_filepath)
            profiler.stop('slurm_req')
        except ConnectionError as err:
            # reformat the exception
            raise ValueError("connection error while trying to connect to "
                             "{url}: {error}".format(url=url, error=err))

        if resp.status_code == 404:
            raise IndexError("job ID {jobid} not found in API {api}"
                             .format(jobid=job, api=self.base_url))

        if resp.status_code == 403:
            logger.debug("Error 403 received: %s", resp.content)
            if firsttime:
                # We probably get this error because of invalidated token.
                # Invalidate cache, trigger check_auth() and call this method
                # again.
                logger.info("token in cache invalidated")
                self.auth_token = None
                self.auth_enabled = None
                self.cache.invalidate()
                return self.job_params(job, firsttime=False)
            else:
                # We have already tried twice. This means the app is not able
                # to auth on slurm-web API with current params. Just throw the
                # error and give-up here.
                raise Exception("get 403/forbidden from {url} with new token"
                                .format(url=self.base_url))
        try:
            json_job = json.loads(resp.text)
        except ValueError:
            # reformat the exception
            raise ValueError("not JSON data for GET {url}"
                             .format(url=url))
        return json_job
