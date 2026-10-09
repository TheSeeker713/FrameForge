"""Override Eporner so the video API receives player.hash, not the user hash."""

from __future__ import annotations

from yt_dlp.extractor.eporner import EpornerIE as _EpornerIE

from frameforge.download.eporner import select_eporner_hash
from frameforge.download.output_path import install_two_word_filenames

install_two_word_filenames()

__all__ = ["EpornerIE"]


class EpornerIE(_EpornerIE):
    def _real_extract(self, url):
        original = self._search_regex

        def _search_regex(pattern, string, name, *args, **kwargs):
            if name == "hash":
                chosen = select_eporner_hash(string)
                if chosen:
                    return chosen
            return original(pattern, string, name, *args, **kwargs)

        self._search_regex = _search_regex
        try:
            return super()._real_extract(url)
        finally:
            self._search_regex = original
