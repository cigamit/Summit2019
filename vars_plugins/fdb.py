
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


import os
from ansible import constants as C
from ansible.errors import AnsibleParserError
from ansible.module_utils._text import to_bytes, to_native, to_text
from ansible.plugins.vars import BaseVarsPlugin
from ansible.inventory.host import Host
from ansible.inventory.group import Group
from ansible.utils.vars import combine_vars
import ConfigParser

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    HAS_PSYCOPG2 = False
else:
    HAS_PSYCOPG2 = True

import ansible.module_utils.postgres as pgutils
from ansible.module_utils.database import SQLParseError, pg_quote_identifier


class VarsModule(BaseVarsPlugin):

    def get_vars(self, loader, path, entities, cache=True):
        if not isinstance(entities, list):
            entities = [entities]
        self.get_config()

        pgutils.ensure_libs(sslrootcert="")
        db_connection = psycopg2.connect(database=self.db, **self.kw)

        # Enable autocommit so we can create databases
        if psycopg2.__version__ >= '2.4.2':
            db_connection.autocommit = True
        else:
            db_connection.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = db_connection.cursor(cursor_factory=psycopg2.extras.DictCursor)

        data = {}
        for entity in entities:
            if isinstance(entity, Host):
                id = self.get_host_id(cursor, self.db, entity.name)
                query = "SELECT fact, data FROM facts WHERE host=%(id)s"
                cursor.execute(query, {'id': id})
                new_data = cursor.fetchall()
                data = combine_vars(data, dict(new_data))
#            elif isinstance(entity, Group):
        return data

    def get_host_id(self, cursor, db, hostname):
        query = "SELECT id FROM hosts WHERE name=%(hostname)s"
        result = cursor.execute(query, {'hostname': hostname})

        if cursor.rowcount == 1:
            id = cursor.fetchone()
        else:
            query = "INSERT INTO hosts (name) VALUES (%(hostname)s); commit;"
            result = cursor.execute(query, {'hostname': hostname})
            query = "SELECT id FROM hosts WHERE name=%(hostname)s"
            cursor.execute(query, {'hostname': hostname})
            id = cursor.fetchone()
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


