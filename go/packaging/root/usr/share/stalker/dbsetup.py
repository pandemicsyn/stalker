"""This module sets up the necessary database and tables in rethinkdb for
stalkerd to operate"""

import argparse
import rethinkdb as r
from rethinkdb.errors import ReqlDriverError

def cliparse():
    """sets up and parses the cli arguments"""
    parser = argparse.ArgumentParser(description="Setup stalker database in "
                                     "rethinkdb for stalkerd")
    parser.add_argument("--host", help="hostname to connect to rethinkdb on",
                        default="localhost")
    parser.add_argument("--port", help="port to connect to rethinkdb on", type=int,
                        default=28015)
    parser.add_argument("--db", help="name of stalker database",
                        default="stalker")
    parser.add_argument("--drop", help="drop existing tables",
                        action="store_true")
    args = parser.parse_args()
    return args

def conn_rethinkdb(host, port):
    """connect to rethinkdb"""
    try:
        r.connect(host, port).repl()
    except ReqlDriverError as error:
        print "Error connecting to RethinkDB:", error
        exit(1)

def get_dblist():
    """get list of databases in rethinkdb"""
    return r.db_list().run()

def get_tables(dbname):
    """get list of tables in rethinkdb stalker database"""
    return r.db(dbname).table_list().run()

def drop_tables(dbname):
    """drop all tables"""
    for table in get_tables(dbname):
        print r.db(dbname).table_drop(table).run()

def get_table_indexes(dbname, tablename):
    """get list of indexes on a table"""
    return r.db(dbname).table(tablename).index_list().run()

def create_db(dbname):
    """create stalker database if it does not exist"""
    if dbname not in get_dblist():
        print r.db_create(dbname).run()

def create_table_indexes(dbname):
    """create all necessary table indexes for stalkerd in database"""
    tables = get_tables(dbname)
    tables_and_indexes = {"hosts": ["hostname"],
                          "checks": ["in_maintenance", "next", "pending",
                                     "status", "suspended"],
                          "users": ["username"],
                          "state_log": ["hostname", "check"],
                          "notifications": ["cid", "hostname", "check"],
                          "notes": ["cid", "hostname", "check"]}

    for table, indexes in tables_and_indexes.iteritems():
        if table not in tables:
            print r.db(dbname).table_create(table).run()
        table_indexes = get_table_indexes(dbname, table)
        for index in indexes:
            if index not in table_indexes:
                print r.db(dbname).table(table).index_create(index).run()

def main():
    """main driver function"""
    args = cliparse()
    conn_rethinkdb(args.host, args.port)
    create_db(args.db)
    if args.drop:
        drop_tables(args.db)
    create_table_indexes(args.db)

if __name__ == "__main__":
    main()
