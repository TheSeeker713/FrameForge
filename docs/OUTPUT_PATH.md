# Output path after yt-dlp exit 0

Job 92 (`https://www.youtube.com/watch?v=Zy7EXDONlTY`) failed three times with:

- `returncode: 0`
- `Downloaded file not found for <url>`
- `category: unknown`
- cookies attached — not an auth failure
- fail-pause still led with Firefox / cookies

That is a **path-resolution** bug, not login.

## Success path (subprocess)

GUI downloads use a killable `python -m yt_dlp` process (`YtDlpDownloader._download_subprocess`), not in-process `YoutubeDL`.

1. **argv `-o`** is an **absolute** template:

   `output_dir / "%(title).200B [%(id)s].%(ext)s"`

   e.g. `%USERPROFILE%\Downloads\FrameForge\youtube\Title [Zy7EXDONlTY].mp4`

2. **`cwd`** is the same `output_dir` (`FrameForge\youtube`). Absolute `-o` plus cwd is redundant (`youtube` vs `youtube\file`). yt-dlp treats an absolute template as absolute; it does not usually double-join. Relative `--print` paths are still resolved against **Python’s process cwd**, not `output_dir`.

3. **`--print` order:**

   - `after_move:%(filepath)s` — post-merge / post-move path (often `NA` if nothing moved)
   - `%(filepath)s` — may be the **pre-merge** fragment (`Title [id].f137.mp4`) that ffmpeg then deletes
   - `%(title)s`, `%(extractor_key)s`, `%(id)s`

4. **Stdout parser** (`printed` list) only keeps lines that:

   - do not start with `[` (YouTube titles like `[Official] …` **drop the filepath**)
   - do not contain ` at ` (titles / paths like `Look at this [id].mp4` **never recorded**)
   - do not contain `ETA`, `at `, or `%`

   Then it does `Path(item).is_file()` **without** joining `output_dir`. A relative print of `Title [id].mp4` is looked up in the GUI cwd (repo / System32 / user profile), not `FrameForge\youtube`.

5. **Fallback glob** (only if that fails): `output_dir.glob("*")` with suffix `.mp4/.mkv/.webm/.m4a` and **mtime &lt; 600s**. It does **not** search by video id. Sidecars (`.part`, `.ytdl`, `.temp`) are excluded only because their suffixes differ.

6. **`download_path`** is set in `make_download_handler` from `DownloadResult.path` after a successful return. If `_download_subprocess` raises `FileNotFoundError`, the job is failed and never gets a path.

7. **`--download-archive`** (`FrameForge\archive\ytdlp-archive.txt`): yt-dlp **writes the id when the download itself succeeds**, before FrameForge looks for the file. Exit 0 + “already recorded in the archive” on retry means **no new file and no `--print` path**. The 600s glob can miss the first copy (wrong dir, filtered print, or retry after 10 minutes). SQLite `download_archive` is a second cache; Job 92 never reached `add_archive` because the handler raised.

8. **aria2 / merge:** transfer may finish as `.part` / `fNNN` fragments; `--merge-output-format mp4` produces the final name. The parser can latch onto a deleted fragment path and ignore the merged `*[id].mp4`.

9. **Title sanitization / emoji / Windows illegal chars:** yt-dlp sanitizes the on-disk name. `--print` may disagree (encoding replacement, truncated `%(title).200B` mid-emoji). Id-based glob is the reliable match.

10. **Classification:** `FileNotFoundError: Downloaded file not found for …` matched nothing, became **`unknown`**, which **fail-pauses** with Firefox/cookies as primary. Wrong.

## Required recovery (v0.5.9)

When `returncode == 0` and the primary parsed path is missing, recover in order:

1. Normalize `--print` after_move / filepath (absolute, or `output_dir / relative`; skip `NA`).
2. Glob `output_dir` for `*[video_id].*` excluding `.part` / `.ytdl` / `.temp` / `.aria2` / `.info.json`.
3. Glob recent `.mp4/.webm/.mkv` in that dir whose name contains the id.
4. If `*.info.json` exists, read `_filename` / `filepath` / `filename`.

If a real media file is found → **completed**, set `download_path`. Do not fail.

If the yt-dlp archive lists the id but no file is on disk → **`output_missing`** (archive orphan). Message: “Archive lists this video but the file is missing on disk.” Retry once with `--no-download-archive` / ignore SQLite archive for that job.

If truly no file → **`output_missing`**, never `unknown`, never auth/cookies primary. Fail-pause actions: Retry (force if orphan) / Open folder / Skip & resume / Stop / Copy report.

Invocation snapshot: `resolved_path`, `recovery_method`, `archive_hit`.
