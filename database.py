import sqlite3
from contextlib import contextmanager

DB_PATH = 'tweets.db'


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                twitter_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS keywords (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                word TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS tweets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tweet_id TEXT UNIQUE NOT NULL,
                username TEXT NOT NULL,
                content TEXT NOT NULL,
                tweet_url TEXT NOT NULL,
                matched_keywords TEXT NOT NULL,
                tweeted_at TIMESTAMP,
                found_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS scrape_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                finished_at TIMESTAMP,
                status TEXT,
                tweets_found INTEGER DEFAULT 0,
                error_message TEXT
            );
            CREATE TABLE IF NOT EXISTS credentials (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                auth_token TEXT,
                ct0 TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')


# --- Accounts ---

def get_accounts():
    with get_db() as conn:
        rows = conn.execute('SELECT * FROM accounts ORDER BY username').fetchall()
        return [dict(r) for r in rows]


def get_account_count():
    with get_db() as conn:
        return conn.execute('SELECT COUNT(*) FROM accounts').fetchone()[0]


def add_account(username):
    with get_db() as conn:
        conn.execute('INSERT OR IGNORE INTO accounts (username) VALUES (?)', (username,))


def remove_account(account_id):
    with get_db() as conn:
        conn.execute('DELETE FROM accounts WHERE id = ?', (account_id,))


def update_account_twitter_id(username, twitter_id):
    with get_db() as conn:
        conn.execute('UPDATE accounts SET twitter_id = ? WHERE username = ?', (twitter_id, username))


# --- Keywords ---

def get_keywords():
    with get_db() as conn:
        rows = conn.execute('SELECT * FROM keywords ORDER BY word').fetchall()
        return [dict(r) for r in rows]


def add_keyword(word):
    with get_db() as conn:
        conn.execute('INSERT OR IGNORE INTO keywords (word) VALUES (?)', (word.lower(),))


def remove_keyword(keyword_id):
    with get_db() as conn:
        conn.execute('DELETE FROM keywords WHERE id = ?', (keyword_id,))


# --- Tweets ---

def store_tweets(tweet_list):
    count = 0
    with get_db() as conn:
        for t in tweet_list:
            try:
                conn.execute(
                    '''INSERT OR IGNORE INTO tweets
                       (tweet_id, username, content, tweet_url, matched_keywords, tweeted_at)
                       VALUES (?, ?, ?, ?, ?, ?)''',
                    (t['tweet_id'], t['username'], t['content'],
                     t['tweet_url'], t['matched_keywords'], t['tweeted_at'])
                )
                if conn.execute('SELECT changes()').fetchone()[0] > 0:
                    count += 1
            except Exception:
                pass
    return count


def get_tweets(account_filter='', keyword_filter='', date_from='', date_to=''):
    query = 'SELECT * FROM tweets WHERE 1=1'
    params = []
    if account_filter:
        query += ' AND username = ?'
        params.append(account_filter)
    if keyword_filter:
        query += ' AND matched_keywords LIKE ?'
        params.append(f'%{keyword_filter}%')
    if date_from:
        query += ' AND tweeted_at >= ?'
        params.append(date_from)
    if date_to:
        query += ' AND tweeted_at <= ?'
        params.append(date_to + ' 23:59:59')
    query += ' ORDER BY tweeted_at DESC'
    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def get_stats():
    with get_db() as conn:
        total = conn.execute('SELECT COUNT(*) FROM tweets').fetchone()[0]
        accs  = conn.execute('SELECT COUNT(DISTINCT username) FROM tweets').fetchone()[0]
        kws   = conn.execute('SELECT COUNT(*) FROM keywords').fetchone()[0]
        return {'total_tweets': total, 'accounts_with_matches': accs, 'total_keywords': kws}


# --- Scrape runs ---

def start_scrape_run():
    with get_db() as conn:
        cur = conn.execute("INSERT INTO scrape_runs (status) VALUES ('running')")
        return cur.lastrowid


def finish_scrape_run(run_id, status, tweets_found, error=None):
    with get_db() as conn:
        conn.execute(
            '''UPDATE scrape_runs
               SET finished_at = CURRENT_TIMESTAMP, status = ?, tweets_found = ?, error_message = ?
               WHERE id = ?''',
            (status, tweets_found, error, run_id)
        )


def get_last_run():
    with get_db() as conn:
        row = conn.execute(
            'SELECT * FROM scrape_runs ORDER BY started_at DESC LIMIT 1'
        ).fetchone()
        return dict(row) if row else None


def get_last_successful_run():
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM scrape_runs WHERE status = 'success' ORDER BY finished_at DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None


# --- Credentials ---

def save_credentials(username, auth_token, ct0):
    with get_db() as conn:
        conn.execute('DELETE FROM credentials')
        conn.execute(
            'INSERT INTO credentials (id, username, auth_token, ct0) VALUES (1, ?, ?, ?)',
            (username, auth_token, ct0)
        )


def get_credentials():
    with get_db() as conn:
        row = conn.execute('SELECT * FROM credentials WHERE id = 1').fetchone()
        return dict(row) if row else None
