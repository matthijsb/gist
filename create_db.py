import sqlite3
import argparse

from urllib.request import pathname2url


ap = argparse.ArgumentParser()
ap.add_argument("--db_name", required=True, help="the db file")

params = vars(ap.parse_args())


try:
    dburi = 'file:{}?mode=rw'.format(pathname2url(params["db_name"]))
    connection = sqlite3.connect(dburi, uri=True)
except sqlite3.OperationalError:
    connection = sqlite3.connect(params["db_name"])

cursor = connection.cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS query (id INTEGER PRIMARY KEY, uuid CHAR(32), prompt TEXT, url TEXT, article_count INT, match_count INT)")   #TODO: deprecate match_count
cursor.execute("CREATE TABLE IF NOT EXISTS papers (id INTEGER PRIMARY KEY, uuid CHAR(32), query_id INT, url TEXT, title TEXT, abstract TEXT, page_nr INT, article_nr INT, status INT DEFAULT 1, avg_score REAL)")
cursor.execute("CREATE TABLE IF NOT EXISTS failed_pages(id INTEGER PRIMARY KEY, uuid CHAR(32), query_id INT, url TEXT)")

cursor.execute("CREATE TABLE IF NOT EXISTS llm_prompt(id INTEGER PRIMARY KEY, uuid CHAR(32), prompt TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS llm_review(id INTEGER PRIMARY KEY, uuid CHAR(32), prompt_id, paper_id INT, raw TEXT, reason TEXT, score REAL)")

for table in ["query","papers","failed_pages",'llm_prompt','llm_review']:
    trigger_name = f"trigger_{table}_uuid"

    check_trigger_sql = f"select count(*) from sqlite_master where type = 'trigger' and name = '{trigger_name}'"
    cursor.execute(check_trigger_sql)
    trigger_exists = cursor.fetchone()
    if trigger_exists[0] == 0:
        trigger_sql = f"""
        CREATE TRIGGER {trigger_name}
        AFTER INSERT ON {table}
        FOR EACH ROW
        WHEN (NEW.uuid IS NULL OR NEW.uuid == '')
        BEGIN
           UPDATE {table} SET uuid = (select lower(hex( randomblob(4)) || '-' || hex( randomblob(2))
                     || '-' || '4' || substr( hex( randomblob(2)), 2) || '-'
                     || substr('AB89', 1 + (abs(random()) % 4) , 1)  ||
                     substr(hex(randomblob(2)), 2) || '-' || hex(randomblob(6))) ) WHERE rowid = NEW.rowid;
        END;"""
        cursor.execute(trigger_sql)

