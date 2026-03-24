# Output Schema

All bundled scripts print JSON with `ensure_ascii=False` and `indent=2`.

When a script needs to sync cache data first, progress logs are written to `stderr`; the JSON schema on `stdout` is unchanged.

## `search_forum.py`

Returns:

- `query`
- `mode`
- `page`
- `search_context`
- `topic_count`
- `post_count`
- `user_count`
- `group_count`
- `tag_count`
- `category_count`
- `has_more_full_page_results`
- `topics[]`
- `posts[]`

## `trace_author.py`

Returns:

- `author`
- `keyword`
- `query`
- `live_search`
- `topic_candidates[]`
- `cached_topics[]`

## `inspect_topic.py`

Returns:

- `topic_id`
- `title`
- `topic_posts_count`
- `db_post_count`
- `json_page_count`
- `raw_page_count`
- `media_image_count`
- `image_file_count`
- `last_posted_at`
- `last_sync_status`
- `last_sync_mode`
- `last_sync_finished_at`
- `cache_path`
- `issues`
- `usable_for_analysis`
- `usable_for_export`
- `has_issues`

## `ensure_cached.py`

Returns:

- `topic_id`
- `cache_hit_before`
- `cache_ready_after`
- `sync_executed`
- `effective_mode`
- `sync_result`
- `inspect_before`
- `inspect_after`

## `query_topic.py`

Returns:

- `topic_id`
- `title`
- `total_hits`
- `ensure_cache`
- `posts[]`

## `summarize_topic.py`

Returns:

- `topic_id`
- `title`
- `time_range`
- `post_count_in_scope`
- `top_authors`
- `top_keywords`
- `key_posts`
- `image_post_numbers`
- `summary`
- `ensure_cache`

## `export_topic.py`

Returns:

- `topic_id`
- `filename`
- `topic_dir`
- `save_dir`
- `raw_seconds`
- `image_seconds`
- `attachment_seconds`
- `video_seconds`
- `audio_seconds`
- `total_seconds`
- `ensure_cache`
