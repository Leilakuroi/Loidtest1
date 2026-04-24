from datetime import datetime, timedelta, timezone

from deep_translator import GoogleTranslator
from thefuzz import fuzz
from twscrape import API


def _expand_keywords(keywords: list[str]) -> dict[str, str]:
    """
    Expand base keywords into translated / synonym-like variants.
    Returns a map of expanded keyword -> original keyword.
    """
    translator_en_to_ja = GoogleTranslator(source="en", target="ja")
    translator_ja_to_en = GoogleTranslator(source="ja", target="en")

    expanded_to_original: dict[str, str] = {}

    for raw_kw in keywords:
        base_kw = (raw_kw or "").strip()
        if not base_kw:
            continue

        variants = {base_kw}
        lowered = base_kw.lower()
        variants.add(lowered)

        # Lightweight synonym-like variants without external API calls.
        for token in (" ", "-", "_"):
            if token in base_kw:
                variants.add(base_kw.replace(token, ""))

        try:
            ja = translator_en_to_ja.translate(base_kw)
            if ja:
                variants.add(ja.strip())
        except Exception:
            pass

        try:
            en = translator_ja_to_en.translate(base_kw)
            if en:
                variants.add(en.strip())
                variants.add(en.strip().lower())
        except Exception:
            pass

        for variant in variants:
            normalized = variant.strip().lower()
            if normalized:
                expanded_to_original.setdefault(normalized, base_kw)

    return expanded_to_original


async def setup_account(username: str, auth_token: str, ct0: str):
    """Cookie-based auth — bypasses Cloudflare entirely."""
    api = API()

    try:
        await api.pool.delete_accounts(username)
    except Exception:
        pass

    await api.pool.add_account(
        username=username,
        password="n/a",
        email=f"{username}@placeholder.com",
        email_password="",
        cookies=f"auth_token={auth_token}; ct0={ct0}",
    )

    all_accounts = await api.pool.get_all()
    matched = next((a for a in all_accounts if a.username.lower() == username.lower()), None)
    if not matched or not matched.active:
        await api.pool.delete_accounts(username)
        error = getattr(matched, 'error_msg', None) or 'cookies may be invalid or expired'
        raise ValueError(f"Account @{username} not activated: {error}")


async def _reactivate_if_needed(api: API, db) -> None:
    """
    twscrape marks the scraping account inactive on any 403 / error-32 response.
    Since we have the cookies saved locally, we can transparently re-add the
    account so the rest of the scrape run continues without manual intervention.
    """
    creds = db.get_credentials()
    if not creds:
        return

    username = creds['username']
    accounts = await api.pool.get_all()
    matched = next((a for a in accounts if a.username.lower() == username.lower()), None)

    if matched and matched.active:
        return

    print(f'[scraper] @{username} became inactive — re-activating from saved credentials')
    try:
        await api.pool.delete_accounts(username)
    except Exception:
        pass

    await api.pool.add_account(
        username=username,
        password="n/a",
        email=f"{username}@placeholder.com",
        email_password="",
        cookies=f"auth_token={creds['auth_token']}; ct0={creds['ct0']}",
    )


async def _resolve_user_id(api: API, username: str) -> str | None:
    try:
        user = await api.user_by_login(username)
        return str(user.id) if user else None
    except Exception as e:
        print(f'[scraper] Could not resolve @{username}: {e}')
        return None


async def _scrape_user(api: API, username: str, twitter_id: str,
                       expanded_keywords: dict[str, str], since: datetime) -> list[dict]:
    matches = []
    tweet_count = 0
    fuzzy_threshold = 85

    try:
        async for tweet in api.user_tweets(int(twitter_id), limit=200):
            tweet_time = tweet.date
            if tweet_time.tzinfo is None:
                tweet_time = tweet_time.replace(tzinfo=timezone.utc)

            if tweet_time < since:
                print(f'[scraper] @{username}: reached tweet older than cutoff ({tweet_time}), stopping')
                break

            tweet_count += 1
            print(f'[scraper] @{username} tweet #{tweet_count} [{tweet_time}]: {tweet.rawContent[:120]!r}')

            content_lower = tweet.rawContent.lower()
            matched: set[str] = set()
            for expanded_kw, base_kw in expanded_keywords.items():
                if fuzz.partial_ratio(expanded_kw, content_lower) >= fuzzy_threshold:
                    matched.add(base_kw)

            if matched:
                matched_sorted = sorted(matched)
                print(f'[scraper] @{username}: MATCH on {matched_sorted}')
                matches.append({
                    'tweet_id': str(tweet.id),
                    'username': username,
                    'content': tweet.rawContent,
                    'tweet_url': f'https://twitter.com/{username}/status/{tweet.id}',
                    'matched_keywords': ', '.join(matched_sorted),
                    'tweeted_at': tweet_time.strftime('%Y-%m-%d %H:%M:%S'),
                })
    except Exception as e:
        print(f'[scraper] Error scraping @{username}: {e}')

    print(f'[scraper] @{username}: {tweet_count} tweet(s) checked, {len(matches)} match(es)')
    return matches


def _get_since_datetime(db) -> datetime:
    now = datetime.now(timezone.utc)
    floor = now - timedelta(hours=48)  # always look back at least 48 h
    cap   = now - timedelta(days=7)    # never look back more than 7 days

    last = db.get_last_successful_run()
    if last and last.get('finished_at'):
        since = datetime.fromisoformat(last['finished_at'])
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)
        # Use whichever is earlier: last run time or 48 h ago.
        # This means frequent test runs never shrink the window below 48 h.
        return max(min(since, floor), cap)

    return floor


async def scrape_all(accounts: list[dict], keywords: list[dict]) -> list[dict]:
    import database as db

    api = API()
    keyword_words = [k['word'] for k in keywords]
    expanded_keywords = _expand_keywords(keyword_words)
    print(f'[scraper] Expanded {len(keyword_words)} keyword(s) into {len(expanded_keywords)} variant(s)')
    since = _get_since_datetime(db)

    all_matches = []
    for account in accounts:
        # Re-activate the scraping account if a previous request got it marked
        # inactive (twscrape marks inactive on any 403 / auth error response).
        await _reactivate_if_needed(api, db)

        username = account['username']
        twitter_id = account.get('twitter_id')

        if not twitter_id:
            twitter_id = await _resolve_user_id(api, username)
            if twitter_id:
                db.update_account_twitter_id(username, twitter_id)

        if not twitter_id:
            print(f'[scraper] Skipping @{username} — could not resolve user ID')
            continue

        # Re-activate again: the user-ID lookup might have triggered a 403 too.
        await _reactivate_if_needed(api, db)

        matches = await _scrape_user(api, username, twitter_id, expanded_keywords, since)
        print(f'[scraper] @{username}: {len(matches)} match(es)')
        all_matches.extend(matches)

    return all_matches
