# Private Library

Local discretion only. **No cloud, no recovery email, no “military-grade” claims.**

## What it does

1. Set a Private password (PBKDF2-HMAC-SHA256 stored in SQLite settings). Session unlock remembers it until quit.
2. **Send to Private** **copies** selected Library files (originals stay until you choose otherwise).
3. Each copy is packed into a **password-protected zip** (traditional ZipCrypto — the same scheme Python’s `zipfile` can read with `pwd=`).
4. Optional disguise: rename the zip to `.ffpriv` (or another extension). The catalog stores the real path. Casual browsing will not show a `.zip`; this is not remote security.
5. After packing: **Keep** originals, **Delete (Recycle Bin)**, or **Move** them to another folder (for example an SD card).

## Honest limits

- A renamed extension hides the file from casual browsing.
- The password protects zip contents against someone who does not know it.
- This is **not** a remote-security or anti-forensics product.
- Forgotten password cannot be recovered by email. Optional recovery-key file is out of scope for v0.6.

## Play / Remove / Export

Private UI stays locked until the password is entered. Play extracts to a temp folder under `library_root/Private/play/` and opens the default player. Remove deletes the private container from the index (and the packed file). Export copies the container out.
