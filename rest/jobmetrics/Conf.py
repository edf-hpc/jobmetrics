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

import ConfigParser
from StringIO import StringIO

# valid periods with their associated interval group time
periods = {'1h': '10s',
           '6h': '30s',
           '24h': '120s'}


class Conf(object):

    def __init__(self, fpath='/etc/jobmetrics/jobmetrics.conf'):

        defaults = StringIO(
            "[global]\n"
            "cache = /var/cache/jobmetrics/jobmetrics.data\n"
            "log = /var/log/jobmetrics/jobmetrics.log\n"
            "tls_verify = true\n"
            "ca_filepath = /etc/ssl/certs/ca-certificates.crt\n"
            "debug = false\n"
            "[influxdb]\n"
            "server = http://localhost:8086\n"
            "db = graphite\n")

        self.conf = ConfigParser.RawConfigParser()
        self.conf.readfp(defaults)
        self.conf.read(fpath)
        self.influxdb_server = self.conf.get('influxdb', 'server')
        self.influxdb_db = self.conf.get('influxdb', 'db')
        self.cache_path = self.conf.get('global', 'cache')
        self.log_path = self.conf.get('global', 'log')
        self.tls_verify = self.conf.getboolean('global', 'tls_verify')
        self.ca_filepath = self.conf.get('global', 'ca_filepath')
        self.debug = self.conf.getboolean('global', 'debug')
        # All sections except influxdb and global are cluster names. So get all
        # sections names minus those two.
        self.clusters = [cluster for cluster in self.conf.sections()
                         if cluster not in ['influxdb', 'global']]

    def api(self, cluster):

        return self.conf.get(cluster, 'api')

    def login(self, cluster):

        # by default, if no login is provided in conf and slurm-web
        # authentication is enabled, the app tries to login as guest.
        try:
            return self.conf.get(cluster, 'login')
        except ConfigParser.NoOptionError:
            return 'guest'

    def password(self, cluster):

        # password is optional (typically, it is useless with guest account)
        # with no sane default.
        try:
            return self.conf.get(cluster, 'password')
        except ConfigParser.NoOptionError:
            return None
