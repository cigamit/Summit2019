# (c) 2014, Brian Coca, Josh Drake, et al
# (c) 2017 Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)


from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

DOCUMENTATION = '''
    cache: memory
    short_description: RAM backed, non persistent
    description:
        - RAM backed cache that is not persistent.
        - This is the default used if no other plugin is specified.
        - There are no options to configure.
    version_added: historical
    author: core team (@ansible-core)
'''
import os
import ConfigParser

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    HAS_PSYCOPG2 = False
else:
    HAS_PSYCOPG2 = True

from ansible.plugins.cache import BaseCacheModule
import ansible.module_utils.postgres as pgutils
from ansible.module_utils.database import SQLParseError, pg_quote_identifier

class CacheModule(BaseCacheModule):

    def __init__(self, *args, **kwargs):
        self._cache = {}
        self.cmdb_facts = {
            "all_ipv4_addresses",
            "architecture",
            "distribution",
            "distribution_major_version",
            "distribution_version",
            "fqdn",
            "hostname",
            "memfree_mb",
            "memtotal_mb",
            "os_family",
            "processor_cores",
            "processor_count",
            "product_name",
            "swapfree_mb",
            "swaptotal_mb",
            "system",
            "system_vendor",
            "virtualization_role",
            "virtualization_type",
            "MyFact",
            "is_db",
            "is_web",
            "db_type",
            "web_type",
            }

        self.get_config()

        pgutils.ensure_libs(sslrootcert="")
        db_connection = psycopg2.connect(database=self.db, **self.kw)

        # Enable autocommit so we can create databases
        if psycopg2.__version__ >= '2.4.2':
            db_connection.autocommit = True
        else:
            db_connection.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
        self.dbcursor = db_connection.cursor(cursor_factory=psycopg2.extras.DictCursor)

    def get(self, key):
        return self._cache.get(key)

    def set(self, key, value):
        id = self.get_host_id(key)
        for a, v in value.items():
            a = a.replace('ansible_', '', 1)
            if a in self.cmdb_facts:
                #print(a, v)
                existing = self.dbcursor.execute("SELECT host FROM facts WHERE host=%(hostname)s AND fact=%(fact)s", {'hostname': id, 'fact': a})
                if self.dbcursor.rowcount == 1:
                    query = "UPDATE facts SET data=%(data)s WHERE host=%(hostname)s AND fact=%(fact)s; commit;"
                else:
                    query = "INSERT INTO facts (host, fact, data) VALUES (%(hostname)s, %(fact)s, %(data)s); commit;"
                result = self.dbcursor.execute(query, {'hostname': id, 'fact': a, 'data': v})
        self._cache[key] = value

    def keys(self):
        return self._cache.keys()

    def contains(self, key):
        return key in self._cache

    def delete(self, key):
        del self._cache[key]

    def flush(self):
        self._cache = {}

    def copy(self):
        return self._cache.copy()

    def __getstate__(self):
        return self.copy()

    def __setstate__(self, data):
        self._cache = data


    def get_host_id(self, hostname):
        query = "SELECT id FROM hosts WHERE name=%(hostname)s"
        result = self.dbcursor.execute(query, {'hostname': hostname})

        if self.dbcursor.rowcount == 1:
            id = self.dbcursor.fetchone()
        else:
            query = "INSERT INTO hosts (name) VALUES (%(hostname)s); commit;"
            result = self.dbcursor.execute(query, {'hostname': hostname})
            query = "SELECT id FROM hosts WHERE name=%(hostname)s"
            self.dbcursor.execute(query, {'hostname': hostname})
            id = self.dbcursor.fetchone()
        return id[0]

    def get_config(self):
        self.config = ConfigParser.SafeConfigParser()
        config_file = '/etc/ansible/fdb.cfg'
        if os.path.exists(config_file):
            self.config.read(config_file)

        self.kw = {}
        if (self.config.has_option('connection', 'host')):
            self.kw["host"] = self.config.get('connection', 'host')

        if (self.config.has_option('connection', 'user')):
            self.kw["user"] = self.config.get('connection', 'user')

        if (self.config.has_option('connection', 'password')):
            self.kw["password"] = self.config.get('connection', 'password')

        if (self.config.has_option('connection', 'port')):
            self.kw["port"] = self.config.get('connection', 'port')

        if (self.config.has_option('connection', 'sslmode')):
            self.kw["sslmode"] = self.config.get('connection', 'sslmode')

        if (self.config.has_option('connection', 'db')):
            self.db = self.config.get('connection', 'db')


