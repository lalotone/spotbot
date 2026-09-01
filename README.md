# spotbot

A Telegram bot that downloads audio from YouTube and YouTube Music URLs. It uses [yt-dlp](https://github.com/yt-dlp/yt-dlp) to fetch the best available audio stream and converts it to MP3 at 320 kbps via FFmpeg. Only explicitly authorized Telegram users can trigger downloads.

## How it works

Send the `/download` command with a YouTube or YouTube Music URL. An optional folder name can be appended to organize the output; if omitted, the file is saved in a `common` folder.

```
/download <URL> [folder name]
```

Examples:

```
/download https://www.youtube.com/watch?v=... Pink Floyd
/download https://music.youtube.com/watch?v=...
```

### Downloading a list of URLs

Send the bot a single file (a `.txt` with one URL per line) and write the command as the file's **caption**:

```
/download                      (caption of the attached .txt)
/download My Mixed Bag         (caption + override the output folder)
```

Every URL in the file is downloaded into the `various` folder by default; the folder name in the caption overrides that. Blank lines and `#` comments are ignored, and invalid lines are skipped with a warning.

Example file content:

```
https://www.youtube.com/watch?v=...
https://music.youtube.com/watch?v=...
# comment lines are ignored
```

List files are limited to 512 KB.

Downloaded files are placed under `DOWNLOAD_FOLDER/<folder_name>/` as `<title>.mp3`. Playlists are supported — individual failures are skipped rather than aborting the whole download. Only one download (single or list) runs at a time; further requests wait their turn. Progress is shown by editing the status message, and a summary is posted when a list finishes.

## Configuration

The bot is configured entirely through environment variables:

| Variable | Description |
|---|---|
| `TELEGRAM_TOKEN` | Bot token from [@BotFather](https://t.me/BotFather) |
| `USER_IDS` | Comma-separated list of authorized Telegram user IDs |
| `DOWNLOAD_FOLDER` | Absolute path where music files will be saved |

## Building the Docker image

Requires Docker with [buildx](https://docs.docker.com/buildx/working-with-buildx/) for cross-platform builds. Enable it once if needed:

```sh
docker buildx create --use
```

| Target | Platform | Use case |
|---|---|---|
| `make build` | native | local development |
| `make build-amd64` | linux/amd64 | standard x86 servers |
| `make build-arm64` | linux/arm64 | Raspberry Pi 4/5 (64-bit OS) |
| `make build-armv7` | linux/arm/v7 | Raspberry Pi 2/3 (32-bit OS) |
| `make build-multi` | amd64 + arm64 + armv7 | multi-arch local image |
| `make push` | amd64 + arm64 + armv7 | build and push to a registry |

The image name and tag can be overridden:

```sh
make build-arm64 IMAGE=myuser/spotbot TAG=v1.0
```

## Running

```sh
docker run -d \
  -e TELEGRAM_TOKEN=your_token \
  -e USER_IDS=123456789,987654321 \
  -e DOWNLOAD_FOLDER=/music \
  -v /path/to/local/music:/music \
  spotbot:latest
```
