# ZeroStreams

Builds `playlist.m3u` from HLS streams linked on https://roxiestreams.info/.
Python 3.12, standard library only. GitHub Actions refreshes at 00:17, 06:17,
12:17 and 18:17 UTC (08:17, 14:17, 20:17 and 02:17 Philippine time).
GitHub scheduled jobs may be delayed; this is not an exact-time guarantee.

## Install on GitHub

1. Create a repository named `ZeroStreams`, with default branch `main`.
2. Upload this folder's contents, including `.github/workflows/refresh.yml`.
3. Enable Actions if prompted. Run **Refresh live playlist → Run workflow**.
4. After a successful run, copy the Raw URL of `playlist.m3u` into VLC or an
   IPTV player. For a public repository it follows this pattern:
   `https://raw.githubusercontent.com/Zer0Spce/ZeroStreams/main/playlist.m3u`.
   Private repositories require authentication. Do not embed GitHub tokens in a player URL.

## Run locally

```sh
python -m unittest discover -s tests -v
python scraper.py
```

Optional: set `SOURCE_URL` to the current source domain if it changes.

## What counts as live

The scraper follows internal HTML links, reads direct HLS URLs and the site's
`getRandomStream` calls plus its current domain TXT file. It checks the HLS
manifest, rejects VOD/ended manifests, and requests a small part of the latest
segment. Master playlists are followed to media variants. Reachability is a
snapshot; this does not establish whether an event is currently in progress,
verify actual video content, or guarantee uninterrupted playback.

Separate working mirror URLs are retained. Identical URLs are deduplicated.
VLC referrer/user-agent directives are included; other players may ignore them.

`status.json` records crawl errors, unavailable URLs, and pages containing
unsupported embedded players. Encrypted/DRM, authenticated, or iframe-only
sources without a public HLS URL are not extracted. No access controls are
bypassed. Use streams only where you have permission to access them.

An incomplete crawl fails the run and retains the last successfully published
playlist. Check Actions and diagnostics before relying on its freshness. A
complete scan with no reachable streams publishes an empty M3U. Domain changes,
expiring URLs, and changes to the site's player logic may require updates.
Public repository schedules can be disabled after 60 days without activity.

## Initial validation

On 2026-10-05 at 00:31 UTC, the initial scan discovered 43 pages and 42 HLS
URLs. 35 passed live-manifest and segment checks, 7 were unavailable, and
there were no discovery errors or unsupported player pages. All five tests
passed. This result is a snapshot, not a playback guarantee. The schedule
starts only after this workflow is uploaded to GitHub and enabled.
