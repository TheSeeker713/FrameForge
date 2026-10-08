# Library

The library is an index of videos that are already on disk. An album is a link in SQLite. Putting a clip in an album, taking it out, or removing it from the library does not move or delete the file.

Completed downloads are indexed at the path the download already used. The file stays in that folder.

## What an album is

- Create an album: a row in `library_collections` with kind `album`.
- One clip is in one album at a time. Placing it in a second album replaces the first link.
- `place_in_album` updates `library_item_collections` and `primary_collection_id`. The `path` column and the file on disk stay the same.
- Remove from library deletes the index row and the collection link. The file stays.
- Delete file is a separate confirm and sends the file to the Recycle Bin. That is not what remove-from-library does.

## What indexing does

`publish_completed_downloads` adds a `library_items` row whose `path` is the finished download. It does not copy or rename that video into `Library/Uncategorized`.

Scan and “add completed downloads” follow the same rule: index in place.

## What is not the album model

An older onboarding wizard can still copy or rename videos into `Library/Uncategorized`. That wizard is not how albums work. Albums never use it. The v0.6.7 move-field gate stays closed until a real-tree log shows `OK #2+`.

Queue and History are unchanged. They are not the library shelf.

## Storage

Metadata lives in `database/frameforge.db` under the FrameForge home, the same file as the queue. Thumbnails may be cached beside the app. The video file stays where the download wrote it.

Settings keys `library_root` and `library_onboarded` still exist for the older wizard. Resetting library onboarding (`scripts/reset_library.ps1`) clears the index and those flags. It does not delete media files.
