# Devlog

## 2026-10-09 — v0.6.37

Launching the GUI printed three errors. `Window.to_front` is a coroutine and was called and dropped, which only warned. Download and tool subprocesses were decoded as cp1252, so a non-ASCII byte from yt-dlp or FFmpeg killed the reader thread. Those reads are UTF-8 now. The `WinError 10054` line is the Windows event loop shutting down a pipe the other end already closed; that callback is ignored.

## 2026-10-09 — v0.6.36

The Library tab was still the old list plus a dialog that offered to move files. That dialog is gone. Opening Library indexes videos where they already are, and Add videos / Add folder can point at any folder. The WebGL shelf is an owned window over the Library pane, because the earlier color-match embed never found a rectangle Flutter actually paints. yt-dlp 2026.07.04 was past 90 days. First-run setup installs yt-dlp, aria2, FFmpeg, and Deno from a second source when the first one fails. History in the jobs table skips that wizard. Settings can run it again, and a later launch updates a tool that has fallen behind, with a short timed note.

## 2026-10-08 — Library shelf

The Library tab's gray pane was the horizontal list. The WebGL studio was never mounted there. The Library tab now hosts that studio (Cover flow, optical glass, magnetic pull, card comes forward, anamorphic and floor mirror on, film grain off, vignette on) and passes the real library rows. Files stay at their source path. Remove-from-library unlinks. Delete-file is a separate Recycle Bin confirm.

## 2026-10-08 — v0.6.35

Clear from queue sat on the window thread until SQLite accepted the hide. A download writing progress holds that write lock, and the click waited through the busy timeout more than once, so the row stayed for minutes. The row and the Undo banner now update from the queue already on screen. The hide is written on a background thread. Clearing a queued row does not stop the download.

## 2026-10-08 — v0.6.34

Adult downloads were getting their own site folder, and YouTube, X, and Facebook were landing at the downloads root. The app now picks `downloads/porn/<category>/` for adult hosts and `downloads/social/<platform>/<category>/` for those three. A stored `eporner.com` path is remapped on retry. A heading or page category replaces `uncategorized` when one exists. On launch, leftover adult site folders and root-level social folders are folded into that layout. A file the open download is still writing is left alone.

## 2026-10-08 — v0.6.33

Long titles were still being used as filenames. When a name would be longer than 77 characters, the file is now saved as the first two words of the title.

## 2026-10-08 — v0.6.32

The clip downloaded, then yt-dlp tried to write a `.info.json` whose full path was 264 characters. Windows stops at 260, so the job was marked failed and the card called it unclassified. The filename template now leaves room for that JSON sibling, and the JSON itself is stored under metadata/ using the video id.

## 2026-10-08 — v0.6.31

Eporner downloads were all dying on “Authorization failed. Try to reload page,” and the card called that unclassified. yt-dlp issue 17713: the page contains two hashes, and the extractor’s regex takes the first one, which is the session hash. The video API wants player.hash. A commenter posted that one-line regex change and another confirmed it on 2026-09-25. FrameForge now loads that override as a yt-dlp plugin, retries the embed page once, and only then tries cookies.

## 2026-10-08 — v0.6.30

The library docs still described albums as folders that move videos. The contract is now written down and tested: album membership, unlink, and indexing a finished download leave the file path unchanged.

## 2026-10-08 — v0.6.29

The queue needed a first-run reset that would not touch videos or cookies. The new command deletes job and archive rows only, and it stops if a download is still running.

## 2026-10-08 — v0.6.28

Import was reading only the visible Word text, dropping listing-page URLs, and committing one queue row at a time on the window thread. Hyperlink targets are read from the document relationships, wrapped URLs stay one job, and the queue insert is a single transaction. The dialog counts listings, URLs, duplicates, and rows to add.

## 2026-10-08 — v0.6.27

The close button was waiting on SQLite, then sometimes quitting with no confirm when that wait or the dialog failed. The first X now only opens the existing quit dialog. Busy wording comes from the worker thread flag, and Quit is the only control that exits.

## 2026-10-08 — v0.6.26

Eporner’s extractor reads a hash from the page, then asks the site API. Without a browser fingerprint that page is the wrong page, so the API answers “Video is not available” for a video that still plays. Eporner was not impersonated, and the classifier treated that sentence as final. The first request now uses Chrome, and the same sentence retries once as a browser before that job is failed.

## 2026-10-08 — v0.6.25

An unclassified yt-dlp exit was pausing the whole queue and offering cookies, even when the site had not asked anyone to sign in. Pause is now reserved for a login, bot, runtime, or disk wall. Copy report reads the job log written next to the temp folder.

## 2026-10-08 — v0.6.24

Aria2 was attached to every download, including fragmented video and sites that need a browser fingerprint. Those now use the built-in downloader. A blocked aria2 attempt retries once with fewer connections, then once without aria2.

## 2026-10-08 — v0.6.23

A site saying the video is not available was still treated as an unknown failure, so the generic extractor ran and the whole queue paused for cookies. That sentence now fails only that job and the next one starts.

## 2026-10-08 — v0.6.22

Failed downloads were showing a rewritten sentence and dropping the warning yt-dlp had already printed. The card now leads with that extractor line, and the full text is saved under temp/logs.

## 2026-10-07 — v0.6.21

The Library tab was still the old list, so the cover-flow shelf from the design session never appeared in the app. Library now shows that shelf, and albums only change the index. Files stay at their source path.

## 2026-10-07 — v0.6.20

An empty file from the fast downloader was classified as unknown, so the queue paused and asked for cookies even when cookies and impersonation were already in use. That case now retries once with the built-in downloader and does not open the pause dialog.

## 2026-10-07 — Library studio

A local WebGL studio at `design/library-studio` lets the Library look be chosen before any app code changes. Choices, kept looks, discarded looks, and notes write themselves to `docs/LIBRARY_DESIGN_FEEDBACK.md`. Reopening the page restores the in-progress answers. The room is a draped wall and walnut floor; cards use brushed metal, paper fiber, or glass edges around a composed still.

## 2026-10-07 — v0.6.19

The Close to system tray switch did not hide the window. The minimize button now does that, and the download keeps running. The tray icon can reopen the window, pause or resume, start pending downloads, and import a URL list or completed downloads.

## 2026-10-07 — v0.6.18

The app was still creating `%USERPROFILE%\Downloads\FrameForge` (database, cookies, models, thumbnails, temp) after a custom folder had been chosen. That tree is now created only when onboarding explicitly uses the Windows default. A custom pick stores the whole app under `<picked>\FrameForge`.

## 2026-10-07 — v0.6.17

Library rows show thumbnails and play inside the app. Queue and History still open the Windows player. The Flet geolocator plugin is replaced with a no-op so Windows location is not started; coordinates are not read or sent anywhere. When cookies for a failing site are already validated, the queue retries and resumes without the pause dialog.
