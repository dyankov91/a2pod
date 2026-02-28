# X API Integration Design

Replace the `bird` CLI dependency with direct X API v2 calls for fetching post and article content from x.com links.

## Decisions

- **Replace bird entirely** — no fallback, clean removal
- **Content types:** single posts + X Articles (no thread stitching)
- **Token storage:** `~/.config/a2pod/config` under `[x]` section
- **HTTP client:** Python's built-in `urllib` — zero new dependencies

## API Call

```
GET https://api.x.com/2/tweets/{id}
Authorization: Bearer {token}
tweet.fields: note_tweet,article,author_id,created_at,text
expansions: author_id
user.fields: name,username
```

## Content Extraction Priority

1. `data.article.text` — X Articles (long-form)
2. `data.note_tweet.text` — long posts (>280 chars)
3. `data.text` — standard posts

## Title Format

`"@username — post"` or `"@username — article"` depending on content type. Uses display name from `includes.users` when available.

## Config

```ini
[x]
bearer_token = xxxxxxxxxxx
```

## Error Handling

- Missing token: clear message with config instructions
- 401/403: auth error message
- 404: post not found
- 429: rate limit message
- Empty/deleted: falls through to existing MIN_ARTICLE_WORDS check

## Files Changed

- `lib/extractor.py` — rewrite `extract_from_x()`, add `_get_x_bearer_token()`
- `install.sh` — optional X token prompt during setup
- Remove `bird` CLI dependency
