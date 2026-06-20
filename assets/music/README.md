# Background Music for Reels

Drop royalty-free MP3 files into the appropriate pillar folder. The bot picks
one at random each time a Reel is generated for that pillar. If a pillar folder
is empty, it falls back to `default/`. If `default/` is also empty, the Reel is
produced silently.

## Folder → Content pillar

| Folder            | Used for                          |
|-------------------|-----------------------------------|
| `ai_guide/`       | AI Guide posts                    |
| `tech_lifestyle/` | Tech Lifestyle posts              |
| `productivity/`   | Productivity posts                |
| `fitness_tech/`   | Fitness Tech posts                |
| `review/`         | Review posts                      |
| `default/`        | Fallback for any unmatched pillar |

## File requirements

- Format: **MP3** (required — ffmpeg decodes it directly)
- Duration: 30 seconds or longer (the bot loops the track to fit the video)
- Naming: anything — `chill-ambient.mp3`, `track-01.mp3`, etc.
- Put multiple files in a folder to rotate between them randomly

## Recommended sources for royalty-free tracks

- **Pixabay Music** — pixabay.com/music (free, no attribution needed)
- **YouTube Audio Library** — studio.youtube.com/channel/*/music (free for commercial use)
- **Bensound** — bensound.com (free with CC-BY attribution in caption)
- **Free Music Archive** — freemusicarchive.org (filter by CC0 or CC-BY)

## Suggested style by pillar

| Pillar            | Style to look for                                        |
|-------------------|----------------------------------------------------------|
| AI Guide          | Ambient electronic, subtle synth pads, minimal beats    |
| Tech Lifestyle    | Upbeat lo-fi, modern electronic, positive vibes         |
| Productivity      | Lo-fi hip-hop, calm focus music, soft piano             |
| Fitness Tech      | Energetic electronic, motivational beats                |
| Review            | Calm cinematic, soft acoustic, understated background   |
| Default           | Neutral ambient — works across all topics               |
