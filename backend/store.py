"""Small transactional store; jobs include their stable item and option snapshots."""
import json
import sqlite3
import threading
from pathlib import Path


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.connection = sqlite3.connect(str(path), check_same_thread=False)
        self.connection.execute('PRAGMA journal_mode=WAL')
        self.connection.executescript('''
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            PRAGMA user_version=1;
        ''')
        self.connection.commit()

    def get_settings(self):
        with self.lock:
            row = self.connection.execute("SELECT payload FROM settings WHERE key='app'").fetchone()
            return json.loads(row[0]) if row else {}

    def save_settings(self, settings):
        with self.lock, self.connection:
            self.connection.execute('INSERT OR REPLACE INTO settings VALUES (?, ?)', ('app', json.dumps(settings)))

    def jobs(self):
        with self.lock:
            return [json.loads(row[0]) for row in self.connection.execute('SELECT payload FROM jobs')]

    def save_job(self, job):
        with self.lock, self.connection:
            self.connection.execute('INSERT OR REPLACE INTO jobs VALUES (?, ?)', (job['id'], json.dumps(job, ensure_ascii=False)))

    def delete_job(self, job_id):
        with self.lock, self.connection:
            self.connection.execute('DELETE FROM jobs WHERE id=?', (job_id,))

    def close(self):
        with self.lock:
            self.connection.close()
