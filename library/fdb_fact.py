#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright: Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type


ANSIBLE_METADATA = {'metadata_version': '1.1',
                    'status': ['stableinterface'],
                    'supported_by': 'community'}
import os
import pipes
import subprocess
import traceback

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    HAS_PSYCOPG2 = False
else:
    HAS_PSYCOPG2 = True

import ansible.module_utils.postgres as pgutils
from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.database import SQLParseError, pg_quote_identifier
from ansible.module_utils.six import iteritems
from ansible.module_utils._text import to_native
import ConfigParser


class NotSupportedError(Exception):
    pass

class FDBModule():
    def __init__(self, module):

        self.get_config()

        pgutils.ensure_libs(sslrootcert="")
        db_connection = psycopg2.connect(database=self.db, **self.kw)

        # Enable autocommit so we can create databases
        if psycopg2.__version__ >= '2.4.2':
            db_connection.autocommit = True
        else:
            db_connection.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
        self.cursor = db_connection.cursor(cursor_factory=psycopg2.extras.DictCursor)



    def get_host_id(self, hostname):
        query = "SELECT id FROM hosts WHERE name=%(hostname)s"
        result = self.cursor.execute(query, {'hostname': hostname})

        if self.cursor.rowcount == 1:
            id = self.cursor.fetchone()
        else:
            query = "INSERT INTO hosts (name) VALUES (%(hostname)s); commit;"
            result = self.cursor.execute(query, {'hostname': hostname})
            query = "SELECT id FROM hosts WHERE name=%(hostname)s"
            self.cursor.execute(query, {'hostname': hostname})
            id = self.cursor.fetchone()
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


    def get_fact(self, hostname, fact):
        id = self.get_host_id(hostname)
        query = "SELECT data FROM facts WHERE host=%(id)s AND fact=%(fact)s"
        self.cursor.execute(query, {'id': id, 'fact': fact})
        fact = self.cursor.fetchone()
        return fact[0]

    def set_fact(self, hostname, fact, data):
        id = self.get_host_id(hostname)

        query = "SELECT data FROM facts WHERE host=%(id)s AND fact=%(fact)s"
        self.cursor.execute(query, {'id': id, 'fact': fact})
    #    module.fail_json(msg="test: %s" % cursor.rowcount)
        if self.cursor.rowcount == 1:
            existing = self.cursor.fetchone()
            if existing[0] == data:
                return False
            else:
                query = "UPDATE facts SET data=%(data)s WHERE host=%(id)s AND fact=%(fact)s"
                self.cursor.execute(query, {'id': id, 'fact': fact, 'data': data})
                return True
        else:
            query = "INSERT INTO facts (host, fact, data) VALUES (%(id)s, %(fact)s, %(data)s)"
            self.cursor.execute(query, {'id': id, 'fact': fact, 'data': data})
            return True
        return False

    def remove_fact(self, hostname, fact):
        id = self.get_host_id(hostname)
        self.cursor.execute(query, {'db': db})
        return cursor.rowcount == 1

def main():
    argument_spec = {}
    argument_spec.update(dict(
        hostname=dict(required=True),
        fact=dict(default=""),
        data=dict(default=""),
        state=dict(default="present", choices=["remove", "set", "get"]),
    ))

    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=True
    )

    if not HAS_PSYCOPG2:
        module.fail_json(msg="the python psycopg2 module is required")



    hostname = module.params["hostname"]
    fact = module.params["fact"]
    data = module.params["data"]
    state = module.params["state"]
    changed = False

    try:
        fdb = FDBModule(module)

    except pgutils.LibraryError as e:
        module.fail_json(msg="unable to connect to database: {0}".format(to_native(e)), exception=traceback.format_exc())

    except TypeError as e:
        if 'sslrootcert' in e.args[0]:
            module.fail_json(msg='Postgresql server must be at least version 8.4 to support sslrootcert. Exception: {0}'.format(to_native(e)),
                             exception=traceback.format_exc())
        module.fail_json(msg="unable to connect to database: %s" % to_native(e), exception=traceback.format_exc())

    except Exception as e:
        module.fail_json(msg="unable to connect to database: %s" % to_native(e), exception=traceback.format_exc())

    try:
        if state == "remove":
            changed = fdb.remove_fact(hostname, fact)
            module.exit_json(changed=changed, fact=fact)
        elif state == "set":
            changed = fdb.set_fact(hostname, fact, data)
            module.exit_json(changed=changed)
        elif state == "get":
            newfact = fdb.get_fact(hostname, fact)
            changed = False
            facts = { fact: newfact }
            module.exit_json(changed=changed, ansible_facts=facts, fact=fact)

    except NotSupportedError as e:
        module.fail_json(msg=to_native(e), exception=traceback.format_exc())
    except SystemExit:
        # Avoid catching this on Python 2.4
        raise
    except Exception as e:
        module.fail_json(msg="Database query failed: %s" % to_native(e), exception=traceback.format_exc())

    module.exit_json(changed=changed, db=fdb.db)


if __name__ == '__main__':
    main()