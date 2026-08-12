# Formats and convert-to-MP3

## Per-job format

The Settings **format preference** remains the global default (`best` → yt-dlp `bv*+ba/b`).

Each job can override that with **Set format…**:

| Preset | yt-dlp `-f` |
|--------|-------------|
| Best | `bv*+ba/b` |
| ≤1080p | `bv*[height<=1080]+ba/b[height<=1080]/bv*+ba/b` |
| ≤720p | `bv*[height<=720]+ba/b[height<=720]/bv*+ba/b` |
| ≤480p | `bv*[height<=480]+ba/b[height<=480]/bv*+ba/b` |
| Audio-focused | `ba/b` |

The override is stored on the job (`format_preference` column). The download handler passes it into yt-dlp opts / CLI `-f`. Other jobs keep the global default.

## Convert selected → MP3

Eligible: **completed** jobs with a local `download_path` or `output_path`.

FFmpeg default (VBR):

```
ffmpeg -i input -vn -c:a libmp3lame -q:a 2 output.mp3
```

`-q:a 2` is ~190 kbps VBR. Output lands in `%USERPROFILE%\Downloads\FrameForge\converted\<site_key>\` (`job{id}_{stem}.mp3`). See [SITE_FOLDERS.md](SITE_FOLDERS.md).

Conversion is a worker stage (`convert_pending` → `converting` → `completed`) and counts as the single active media stage: it never runs in parallel with download or upscale. The ffmpeg PID is registered for hard cancel / quit policy.

Ineligible selection shows a message and does not crash. Failures use error category `ffmpeg` in the job error panel.
