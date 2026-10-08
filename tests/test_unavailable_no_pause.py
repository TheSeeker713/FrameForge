"""A site that says the video is gone is not a login problem and does not pause the queue."""

from __future__ import annotations

from frameforge.download.recovery import next_recovery_step, should_try_silent_cookies
from frameforge.errors import NOT_AVAILABLE, classify_error, should_fail_pause

SCREENSHOT = (
    "yt-dlp exited with code 1\n"
    "ERROR: [Eporner] yzAUyuvBAJ1: Eporner said: Video is not available\n"
)
NAMED_MISMATCH = "ERROR: [Eporner] yzAUyuvBAJ1: Unable to extract video url"
URL = "https://www.eporner.com/video-yzAUyuvBAJ1/the-greatest-act-of-love-and-charity/"


def test_screenshot_sentence_is_unavailable_and_does_not_pause():
    assert classify_error(SCREENSHOT, url=URL) == NOT_AVAILABLE
    assert should_fail_pause(NOT_AVAILABLE) is False
    assert should_try_silent_cookies(None, SCREENSHOT, URL) is False
    assert (
        next_recovery_step(
            [],
            category=None,
            message=SCREENSHOT,
            url=URL,
            silent_cookies=True,
        )
        is None
    )


def test_named_extractor_does_not_fall_through_to_generic():
    assert (
        next_recovery_step(
            [],
            category="unknown",
            message=NAMED_MISMATCH,
            url="https://example.com/video",
        )
        is None
    )
