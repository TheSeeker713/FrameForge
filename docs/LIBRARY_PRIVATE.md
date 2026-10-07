# Private Library

Local discretion only. **No cloud, no recovery email, no “military-grade” claims.**

## What it does

1. Set a Private password (PBKDF2-HMAC-SHA256 stored in SQLite settings). Session unlock remembers it until quit.
2. **Send to Private** **copies** selected Library files (originals stay until you choose otherwise).
3. Each new copy is packed with **AES-256-GCM**. The key is derived from the Private password (PBKDF2-HMAC-SHA256) and a random salt stored in the file. Packs written earlier with ZipCrypto still open.
4. Optional disguise: rename the file to `.ffpriv` (or another extension). That only changes the extension.
5. After packing: **Keep** originals, **Delete (Recycle Bin)**, or **Move** them to another folder (for example an SD card).

## Honest limits

- A renamed extension hides the file from casual browsing. It is not encryption.
- AES-256-GCM protects the packed bytes from someone who does not know the password. Playback writes a temporary decrypted file and deletes `Private/play` on quit.
- This is **not** a remote-security or anti-forensics product.
- Forgotten password cannot be recovered by email. Optional recovery-key file is out of scope for v0.6.

## Play / Remove / Export

Private UI stays locked until the password is entered. Play extracts to a temp folder under `library_root/Private/play/` and opens the default player. Quit deletes that `play` folder. Remove deletes the private container from the index (and the packed file). Export copies the container out.
