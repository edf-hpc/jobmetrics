import logging, sys
logging.basicConfig(stream=sys.stderr)
sys.path.insert(0, '/usr/share/jobmetrics/restapi')
from app import app as application
