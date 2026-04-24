import asyncio
import csv
import io
import os
import threading

from apscheduler.schedulers.background import BackgroundScheduler
from flask import (Flask, Response, flash, redirect, render_template,
                   request, url_for)

import database
import scraper

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'tweet-monitor-dev-key')

database.init_db()

# Single event loop shared across Flask routes, the scheduler, and twscrape.
# asyncio.run() creates a fresh loop each call, which breaks twscrape's
# aiosqlite connections and internal locks that are bound to the first loop.
_async_loop = asyncio.new_event_loop()
threading.Thread(target=_async_loop.run_forever, daemon=True, name='async-loop').start()


def run_async(coro):
    """Block the calling thread until *coro* completes on the shared loop."""
    future = asyncio.run_coroutine_threadsafe(coro, _async_loop)
    return future.result()

# --- Scheduler ---

scheduler = BackgroundScheduler(daemon=True)


def run_scrape_job():
    run_id = database.start_scrape_run()
    try:
        accounts = database.get_accounts()
        keywords = database.get_keywords()
        if not accounts or not keywords:
            database.finish_scrape_run(run_id, 'skipped', 0)
            return
        results = run_async(scraper.scrape_all(accounts, keywords))
        count = database.store_tweets(results)
        database.finish_scrape_run(run_id, 'success', count)
        print(f'[scheduler] Scrape done — {count} new tweet(s) stored')
    except Exception as e:
        database.finish_scrape_run(run_id, 'error', 0, str(e))
        print(f'[scheduler] Scrape failed: {e}')


scheduler.add_job(run_scrape_job, 'cron', hour=8, minute=0, id='daily_scrape')
scheduler.start()

# --- Routes ---

@app.route('/')
def index():
    return redirect(url_for('config'))


@app.route('/config')
def config():
    next_job = scheduler.get_job('daily_scrape').next_run_time
    return render_template('config.html',
        accounts=database.get_accounts(),
        keywords=database.get_keywords(),
        last_run=database.get_last_run(),
        credentials=database.get_credentials(),
        next_run=next_job,
        account_count=database.get_account_count(),
    )


@app.route('/config/credentials', methods=['POST'])
def set_credentials():
    username = request.form.get('username', '').strip().lstrip('@')
    auth_token = request.form.get('auth_token', '').strip()
    ct0 = request.form.get('ct0', '').strip()

    if not username or not auth_token or not ct0:
        flash('Username, auth_token, and ct0 are all required.', 'danger')
        return redirect(url_for('config'))
    try:
        run_async(scraper.setup_account(username, auth_token, ct0))
        database.save_credentials(username, auth_token, ct0)
        flash(f'Scraping account @{username} verified and configured.', 'success')
    except Exception as e:
        flash(f'Failed to configure account: {e}', 'danger')
    return redirect(url_for('config'))


@app.route('/config/accounts/add', methods=['POST'])
def add_account():
    username = request.form.get('username', '').strip().lstrip('@')
    if not username:
        flash('Username is required.', 'danger')
        return redirect(url_for('config'))
    if database.get_account_count() >= 30:
        flash('Maximum of 30 accounts allowed.', 'danger')
        return redirect(url_for('config'))
    database.add_account(username)
    flash(f'@{username} added.', 'success')
    return redirect(url_for('config'))


@app.route('/config/accounts/remove', methods=['POST'])
def remove_account():
    database.remove_account(request.form.get('id'))
    flash('Account removed.', 'success')
    return redirect(url_for('config'))


@app.route('/config/keywords/add', methods=['POST'])
def add_keyword():
    word = request.form.get('word', '').strip()
    if not word:
        flash('Keyword is required.', 'danger')
        return redirect(url_for('config'))
    database.add_keyword(word)
    flash(f'Keyword "{word.lower()}" added.', 'success')
    return redirect(url_for('config'))


@app.route('/config/keywords/remove', methods=['POST'])
def remove_keyword():
    database.remove_keyword(request.form.get('id'))
    flash('Keyword removed.', 'success')
    return redirect(url_for('config'))


@app.route('/config/run', methods=['POST'])
def manual_run():
    creds = database.get_credentials()
    if not creds:
        flash('Configure a scraping account first.', 'danger')
        return redirect(url_for('config'))
    try:
        run_scrape_job()
        last = database.get_last_run()
        if last and last['status'] == 'success':
            flash(f'Scrape complete — {last["tweets_found"]} new tweet(s) found.', 'success')
        elif last and last['status'] == 'skipped':
            flash('Skipped — no accounts or keywords configured.', 'warning')
        else:
            flash(f'Scrape failed: {last["error_message"] if last else "unknown error"}', 'danger')
    except Exception as e:
        flash(f'Scrape failed: {e}', 'danger')
    return redirect(url_for('config'))


@app.route('/results')
def results():
    account_filter = request.args.get('account', '')
    keyword_filter = request.args.get('keyword', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    return render_template('results.html',
        tweets=database.get_tweets(account_filter, keyword_filter, date_from, date_to),
        accounts=database.get_accounts(),
        keywords=database.get_keywords(),
        stats=database.get_stats(),
        account_filter=account_filter,
        keyword_filter=keyword_filter,
        date_from=date_from,
        date_to=date_to,
    )


@app.route('/results/export')
def export_csv():
    tweets = database.get_tweets(
        request.args.get('account', ''),
        request.args.get('keyword', ''),
        request.args.get('date_from', ''),
        request.args.get('date_to', ''),
    )
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Account', 'Tweet', 'Matched Keywords', 'Tweet Date', 'URL', 'Found At'])
    for t in tweets:
        writer.writerow([
            t['username'], t['content'], t['matched_keywords'],
            t['tweeted_at'], t['tweet_url'], t['found_at'],
        ])
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=tweet_report.csv'},
    )


if __name__ == '__main__':
    app.run(debug=True, use_reloader=False, port=5000)
