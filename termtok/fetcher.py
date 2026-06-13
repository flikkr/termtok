"""Background streaming engines for the video feeds.

A fetcher runs on a daemon thread and keeps an ordered list of video
descriptors a little ahead of the playhead, downloading the next few into a
bounded LRU cache. Two backends share that machinery via :class:`BaseFetcher`:

  * :class:`TikTokFetcher` — discovery via TikTokApi (async + Playwright), since
    TikTok hides its feeds behind a signed web app. The actual mp4 download is
    still done by yt-dlp, because TikTok strips the playable URL from its API.
  * :class:`YouTubeFetcher` — discovery *and* download via yt-dlp. No API key,
    token or browser needed; far simpler and more reliable.

Everything shared with the player thread is guarded by one lock. The player
only reads (``count``/``path``/``label``/``status``); the playhead hint is the
only thing it writes.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
import sys
import threading
import urllib.parse
from dataclasses import dataclass

log = logging.getLogger("termtok.fetcher")

# A YouTube video id is exactly 11 chars; channel ids (UC…) and playlist ids
# (PL…/UU…) are longer and must not be treated as downloadable videos.
_YT_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


@dataclass
class _Desc:
    id: str
    author: str
    desc: str
    url: str | None  # canonical watch URL, used by yt-dlp to download


class BaseFetcher:
    # Keep this many descriptors fetched ahead of the playhead.
    LOOKAHEAD_META = 8
    # Download this many videos beyond the playhead.
    PREFETCH_AHEAD = 4
    # Videos within +/- this of the playhead are never evicted.
    PROTECT = 2
    # Give up on a video after this many failed download attempts.
    MAX_ATTEMPTS = 3
    # Anything smaller than this is a bogus/partial download, not a video.
    MIN_VALID_BYTES = 50_000
    # yt-dlp format: a single progressive mp4 (no merge => no ffmpeg needed).
    YTDLP_FORMAT = "b[ext=mp4]/best[ext=mp4]/best"
    DOWNLOAD_TIMEOUT = 120  # seconds per video

    def __init__(self, cache_dir: str, cache_bytes: int) -> None:
        self.cache_dir = cache_dir
        self.cache_bytes = cache_bytes

        self._lock = threading.Lock()
        self._desc: list[_Desc] = []
        self._files: dict[int, str] = {}  # descriptor index -> cached path
        self._attempts: dict[int, int] = {}
        self._playhead = 0
        self._status: str | None = "connecting…"
        self._exhausted = False

        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._main, name="termtok-fetcher", daemon=True
        )
        os.makedirs(cache_dir, exist_ok=True)

    # -- public, called from the player thread -----------------------------

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def count(self) -> int:
        with self._lock:
            return len(self._desc)

    def path(self, i: int) -> str | None:
        with self._lock:
            return self._files.get(i)

    def label(self, i: int) -> str:
        with self._lock:
            if 0 <= i < len(self._desc):
                d = self._desc[i]
                who = f"@{d.author}" if d.author else ""
                return f"{who}  {d.desc}".strip()
            return ""

    def status(self) -> str | None:
        with self._lock:
            return self._status

    def has_more(self) -> bool:
        with self._lock:
            return not self._exhausted

    def dead(self, i: int) -> bool:
        """True if video ``i`` failed to download and won't be retried."""
        with self._lock:
            return (
                i not in self._files
                and self._attempts.get(i, 0) >= self.MAX_ATTEMPTS
            )

    def set_playhead(self, i: int) -> None:
        with self._lock:
            self._playhead = max(0, i)

    # -- background thread --------------------------------------------------

    def _main(self) -> None:
        log.info(
            "fetcher starting: %s cache_dir=%s cache=%dMB",
            self.describe(), self.cache_dir, self.cache_bytes // (1024 * 1024),
        )
        try:
            self._run()
        except Exception as e:  # noqa: BLE001 - surface any failure to the UI
            log.exception("fetcher crashed")
            with self._lock:
                self._status = f"feed error: {e}"
                self._exhausted = True
        finally:
            log.info(
                "fetcher stopped (known=%d, exhausted=%s)",
                len(self._desc), self._exhausted,
            )

    def describe(self) -> str:
        return "base"

    def _run(self) -> None:
        raise NotImplementedError

    # -- shared download machinery -----------------------------------------

    def _download_targets(self) -> list[int]:
        with self._lock:
            ph = self._playhead
            n = len(self._desc)
            return [
                i
                for i in range(ph, min(ph + self.PREFETCH_AHEAD + 1, n))
                if i not in self._files
                and self._attempts.get(i, 0) < self.MAX_ATTEMPTS
            ]

    def _download_sync(self, i: int) -> None:
        """Ensure video ``i`` is in the cache (runs on a worker thread)."""
        with self._lock:
            if i in self._files or i >= len(self._desc):
                return
            d = self._desc[i]
        path = os.path.join(self.cache_dir, f"{d.id}.mp4")

        # Reuse across runs: adopt a previously cached file if it looks valid.
        if os.path.exists(path) and os.path.getsize(path) >= self.MIN_VALID_BYTES:
            log.debug("cache hit #%d id=%s (%d bytes)", i, d.id, os.path.getsize(path))
            os.utime(path, None)
            with self._lock:
                self._files[i] = path
            self._evict()
            return

        if not d.url:
            log.warning("no URL for #%d id=%s; skipping", i, d.id)
            with self._lock:
                self._attempts[i] = self.MAX_ATTEMPTS
            return

        attempts = self._attempts.get(i, 0) + 1
        log.debug("downloading #%d id=%s @%s via yt-dlp: %s", i, d.id, d.author, d.url)
        rc, err = self._ytdlp(d.url, path)

        if rc != 0 or not os.path.exists(path):
            log.warning(
                "download failed #%d id=%s (attempt %d, rc=%s): %s",
                i, d.id, attempts, rc, (err or "").strip()[-200:],
            )
            with self._lock:
                self._attempts[i] = attempts
                self._status = "download failed (see log)"
            return

        size = os.path.getsize(path)
        if size < self.MIN_VALID_BYTES:
            # e.g. a photo/slideshow post with only an audio track, no video.
            log.warning(
                "download #%d id=%s produced only %d bytes (no video stream?); dropping",
                i, d.id, size,
            )
            try:
                os.remove(path)
            except OSError:
                pass
            with self._lock:
                self._attempts[i] = self.MAX_ATTEMPTS
            return

        log.info("downloaded #%d id=%s (%d bytes)", i, d.id, size)
        with self._lock:
            self._files[i] = path
            self._status = None
        self._evict()

    def _ytdlp(self, url: str, out_path: str) -> tuple[int, str]:
        """Download ``url`` to ``out_path`` (an .mp4) with yt-dlp. Returns (rc, stderr)."""
        template = out_path[: -len(".mp4")] + ".%(ext)s"
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "--impersonate", "chrome",  # needs curl_cffi; harmless if unused
            # Lets yt-dlp fetch & run YouTube's JS "n-challenge" solver (needs a
            # JS runtime like deno/node). Without it many YouTube videos expose
            # zero formats and fail as "This video is not available". No-op for
            # TikTok. The solver lib is downloaded once and cached by yt-dlp.
            "--remote-components", "ejs:github",
            "--no-playlist", "--no-progress", "--no-warnings",
            "-f", self.YTDLP_FORMAT,
            "-o", template,
            url,
        ]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=self.DOWNLOAD_TIMEOUT
            )
            return proc.returncode, proc.stderr
        except subprocess.TimeoutExpired:
            return 1, "yt-dlp timed out"
        except Exception as e:  # noqa: BLE001
            return 1, str(e)

    def _evict(self) -> None:
        """Trim the cache to ``cache_bytes`` (LRU, protecting the playhead)."""
        entries = []
        for name in os.listdir(self.cache_dir):
            if not name.endswith(".mp4"):
                continue
            p = os.path.join(self.cache_dir, name)
            try:
                st = os.stat(p)
            except OSError:
                continue
            entries.append((p, st.st_size, st.st_atime))

        total = sum(size for _, size, _ in entries)
        if total <= self.cache_bytes:
            return

        with self._lock:
            ph = self._playhead
            lo = max(0, ph - self.PROTECT)
            hi = min(len(self._desc), ph + self.PROTECT + 1)
            protected = {self._desc[j].id for j in range(lo, hi)}
            idx_by_id = {self._desc[j].id: j for j in range(len(self._desc))}

        evictable = [e for e in entries if _id_of(e[0]) not in protected]
        evictable.sort(key=lambda e: e[2])  # oldest access first
        for p, size, _ in evictable:
            if total <= self.cache_bytes:
                break
            try:
                os.remove(p)
            except OSError:
                continue
            total -= size
            log.debug("evicted %s (%d bytes), cache now %d bytes", _id_of(p), size, total)
            j = idx_by_id.get(_id_of(p))
            if j is not None:
                with self._lock:
                    self._files.pop(j, None)


class TikTokFetcher(BaseFetcher):
    def __init__(self, mode, arg, cache_dir, cache_bytes, ms_token) -> None:
        super().__init__(cache_dir, cache_bytes)
        self.mode = mode
        self.arg = arg
        self.ms_token = ms_token

    def describe(self) -> str:
        tok = f"present(len={len(self.ms_token)})" if self.ms_token else "MISSING"
        return f"mode=tiktok:{self.mode} arg={self.arg!r} ms_token={tok}"

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._arun())
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            finally:
                loop.close()

    async def _arun(self) -> None:
        from TikTokApi import TikTokApi

        from .log import attach_library_logger

        api = TikTokApi(logging_level=log.getEffectiveLevel())
        async with api:
            attach_library_logger(api.logger)
            browser = os.getenv("TIKTOK_BROWSER", "chromium")
            log.info("creating session (browser=%s)…", browser)
            try:
                await api.create_sessions(
                    ms_tokens=[self.ms_token],
                    num_sessions=1,
                    sleep_after=3,
                    browser=browser,
                )
            except Exception as e:  # noqa: BLE001
                log.exception("session creation failed")
                with self._lock:
                    self._status = f"login failed: {e}"
                    self._exhausted = True
                return

            log.info("session ready; streaming mode=%s arg=%r", self.mode, self.arg)
            with self._lock:
                self._status = None  # connected

            gen = self._feed(api)
            while not self._stop.is_set():
                await self._ensure_meta(gen)
                for i in self._download_targets():
                    if self._stop.is_set():
                        break
                    await asyncio.to_thread(self._download_sync, i)
                await asyncio.sleep(0.08)

    def _feed(self, api):
        big = 10_000  # the library pages internally until hasMore is False
        mode, arg = self.mode, self.arg
        if mode == "trending":
            return api.trending.videos(count=big)
        if mode == "user":
            return api.user(username=arg).videos(count=big)
        if mode == "tag":
            return api.hashtag(name=arg).videos(count=big)
        if mode == "related":

            async def related():
                seed = api.video(url=arg)
                yield seed
                async for v in seed.related_videos(count=big):
                    yield v

            return related()
        raise ValueError(f"unknown feed mode: {mode!r}")

    async def _ensure_meta(self, gen) -> None:
        with self._lock:
            need = self._playhead + self.LOOKAHEAD_META
            have = len(self._desc)
            done = self._exhausted
        while have < need and not done and not self._stop.is_set():
            try:
                v = await gen.__anext__()
            except StopAsyncIteration:
                log.info("feed exhausted at %d video(s)", have)
                with self._lock:
                    self._exhausted = True
                    if not self._desc:
                        log.warning(
                            "feed returned ZERO videos — likely missing/expired "
                            "ms_token, or this feed is blocked"
                        )
                        self._status = (
                            "no videos returned — check ms_token, "
                            "or try --tag/--user"
                        )
                return
            except Exception as e:  # noqa: BLE001
                log.exception("error pulling feed metadata")
                with self._lock:
                    self._status = f"fetch error: {e}"
                    self._exhausted = True
                return
            d = self._descriptor(v)
            with self._lock:
                self._desc.append(d)
                have = len(self._desc)
            log.debug("queued #%d id=%s @%s — %.50s", have - 1, d.id, d.author, d.desc)

    @staticmethod
    def _descriptor(v) -> _Desc:
        data = getattr(v, "as_dict", None) or {}
        author = data.get("author")
        if isinstance(author, dict):
            name = author.get("uniqueId") or author.get("nickname") or ""
        else:
            name = ""
        vid = str(getattr(v, "id", "") or "")
        url = getattr(v, "url", None)
        if not url and name and vid:
            url = f"https://www.tiktok.com/@{name}/video/{vid}"
        return _Desc(
            id=vid,
            author=name,
            desc=(data.get("desc") or "").replace("\n", " ").strip(),
            url=url,
        )


class YouTubeFetcher(BaseFetcher):
    # How many ids to enumerate per yt-dlp flat-playlist call.
    BATCH = 20

    def __init__(self, source_url: str, cache_dir: str, cache_bytes: int) -> None:
        super().__init__(cache_dir, cache_bytes)
        self.source_url = source_url
        self._cursor = 0  # playlist index already enumerated (1-based)
        self._seen: set[str] = set()  # video ids already queued (dedupe)

    def describe(self) -> str:
        return f"mode=youtube url={self.source_url!r}"

    def _run(self) -> None:
        # No session/handshake needed — yt-dlp does everything.
        with self._lock:
            self._status = None
        while not self._stop.is_set():
            self._ensure_meta()
            for i in self._download_targets():
                if self._stop.is_set():
                    break
                self._download_sync(i)
            self._stop.wait(0.1)

    def _ensure_meta(self) -> None:
        with self._lock:
            need = self._playhead + self.LOOKAHEAD_META
            have = len(self._desc)
            done = self._exhausted
        while have < need and not done and not self._stop.is_set():
            start = self._cursor + 1
            end = self._cursor + self.BATCH
            batch, n_raw = self._enumerate(start, end)
            self._cursor = end

            if n_raw == 0:
                log.info("youtube feed exhausted at %d video(s)", have)
                with self._lock:
                    self._exhausted = True
                    if not self._desc:
                        self._status = "no videos found (check the channel/query)"
                return

            added = 0
            with self._lock:
                for d in batch:
                    if d.id in self._seen:  # dedupe within and across batches
                        continue
                    self._seen.add(d.id)
                    self._desc.append(d)
                    added += 1
                have = len(self._desc)
            log.debug(
                "queued %d/%d youtube videos from entries (now %d)", added, n_raw, have
            )
            if n_raw < self.BATCH:  # yt-dlp returned a short page => end of feed
                with self._lock:
                    self._exhausted = True
                return

    def _enumerate(self, start: int, end: int) -> tuple[list[_Desc], int]:
        """Return (video descriptors, raw entry count) for playlist [start:end]."""
        sep = "\x1f"  # unit separator — safe vs titles containing tabs
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "--flat-playlist", "--no-warnings",
            "-I", f"{start}:{end}",
            "--print", f"%(ie_key)s{sep}%(id)s{sep}%(uploader)s{sep}%(title)s",
            self.source_url,
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except Exception as e:  # noqa: BLE001
            log.warning("youtube enumerate failed (%s..%s): %s", start, end, e)
            return [], 0
        if proc.returncode != 0:
            log.warning(
                "yt-dlp enumerate rc=%s: %s", proc.returncode, proc.stderr.strip()[-200:]
            )
            return [], 0

        out: list[_Desc] = []
        n_raw = 0
        for line in proc.stdout.splitlines():
            if not line.strip():
                continue
            n_raw += 1
            ie_key, _, rest = line.partition(sep)
            vid, _, rest = rest.partition(sep)
            author, _, title = rest.partition(sep)
            # Keep only real videos — skip channel (YoutubeTab) / playlist entries.
            if ie_key != "Youtube" or not _YT_VIDEO_ID.match(vid):
                log.debug("skip non-video entry ie_key=%s id=%s", ie_key, vid)
                continue
            out.append(
                _Desc(
                    id=vid,
                    author="" if author in ("", "NA") else author,
                    desc="" if title == "NA" else title,
                    url=f"https://www.youtube.com/shorts/{vid}",
                )
            )
        return out, n_raw


def channel_shorts_url(name: str) -> str:
    return f"https://www.youtube.com/@{name.lstrip('@')}/shorts"


def search_url(query: str) -> str:
    q = urllib.parse.quote(f"{query} #shorts")
    return f"https://www.youtube.com/results?search_query={q}"


def _id_of(path: str) -> str:
    return os.path.splitext(os.path.basename(path))[0]
