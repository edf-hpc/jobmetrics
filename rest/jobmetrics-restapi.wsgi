import logging, sys
logging.basicConfig(stream=sys.stderr)
sys.path.insert(0, '/usr/share/jobmetrics/restapi')
from jobmetrics import app as application
