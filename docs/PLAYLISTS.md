# Playlists

FrameForge expands playlists with a **flat** yt-dlp listing (`extract_flat: in_playlist`) so the picker can show titles quickly without fully extracting every video first.

## Flow

1. Paste a playlist URL and click **Add**.
2. A picker shows the playlist title, entry count, and checkbox rows.
3. **Select all** / **Select none**, then **Enqueue selected**.
4. Each chosen row becomes its own **pending** job. Downloads do **not** start until you press Download.

Jobs store `playlist_id`, `playlist_title`, `playlist_index`, and `playlist_url` in `options_json`. Queue rows show a `PL N` badge. `JobRepository.list_jobs_for_playlist` can filter by playlist id.

## Limits

Initial listing is capped at **500** entries (`PLAYLIST_ENTRY_CAP`). Select-all applies to the fetched page. Virtualization beyond that cap is deferred.

## Sequential

Playlist jobs still obey the single-active-stage rule: one download **or** upscale **or** convert at a time. Enqueue never auto-starts.
