# Hianime with Local MPV
![Python](https://img.shields.io/badge/python-3.12-green)

## Description
A CLI Python tool for streaming anime from hianime.to—the standout site for its superior soft-subbed episodes—straight into your local MPV player. Unlike other anime platforms, this lets you override them with your own, especially people want to use Japanese originals sub fetched via the Jimaku API. Perfect for people wants a lightweight hianime MPV extension with series pinning, history tracking, and seamless multi-language subtitle swaps.

## Project Status
This repository is a fork of the original work by dhilzyi: `https://github.com/dhilzyi`.
The upstream maintainer is moving development to a Go rewrite and plans to archive the Python project. Ongoing updates are in:
[hianime-cli](https://github.com/dhilzyi/hianime-cli)

## Disclaimer
This tool is for educational and personal use only. It demonstrates web scraping and media integration techniques—use responsibly, respect site terms of service, and be mindful of copyrights. I'm not affiliated with any third-party sites or services.

## Introduction
This code was mostly written with AI assistance. I just gave the idea for what to build, then handled some code tweaks and cleanup. It's great for people who want to importing subtitles in other languages and using MPV extensions for hianime.

https://github.com/user-attachments/assets/f8ba7d32-9c6e-48d4-a386-70eb991b6da1

## Shoutouts
- Huge thanks to the [MediaVanced](https://github.com/yogesh-hacker/MediaVanced) repo—this project wouldn't have been possible without it!
- And big props to [aniyomi-extensions]( https://github.com/yuzono/aniyomi-extensions) for the inspiration.

## Features
- 📌 **Pin Series**: Save your favorites for quick access.
- 📺 **Recent History**: Pick up where you left off.
- 🌐 **Jimaku API Integration**: Fetch and import Japanese subtitles.

## Enhancements
Pair this tool with these for an even better experience:
- For automatic subtitle syncing with the English subs from hianime.to, check out [AutoSubSync-MPV](https://github.com/joaquintorres/autosubsync-mpv). It handles unsync subs automatically. Select to 'Sync to another subtitle' then select the sub_english_temp..srt (It should be in the last order and the format is .srt).

## Requirements
- Python 3.12+
- MPV player (install via [official site](https://mpv.io/)) and add to PATH. Test with `mpv --version`
- yt-dlp (download the latest release [here](https://github.com/yt-dlp/yt-dlp/releases) place `yt-dlp.exe` in the same directory as MPV or another PATH directory)
- FFmpeg (install via [official site](https://ffmpeg.org/download.html) or with `winget install ffmpeg`) and add to PATH. Test with `ffmpeg -version`
- Key libraries (via `requirements.txt`): requests (for APIs), beautifulsoup4 (for parsing), etc. Full list in `requirements.txt`

  
## Installation
1. `git clone https://github.com/dhilzyi/hianime-with-local-mpv.git`
2. `cd hianime-with-local-mpv`
3. `pip install -r requirements.txt`

## Usage
```bash
python hianime.py
```
Use `python hianime.py --command` as you can print the raw mpv command for debugging such as using another command mpv.
- Paste an anime URL (e.g., https://hianime.to/watch/one-piece-100).
- Select options like episode, or 'p' to pin to series.
- Choose servers manually or automatically.
- Set your directory for downloaded subtitle in variable SUBTITLE_BASE_DIR. It is "F:/Subtitle" as a default.
- Set your JIMAKU_API_KEY in environment variables.
- Configure Jimaku and viability checks in `config.json`.

## Configuration
Configuration lives in `config.json` at the repo root.

Example:
```json
{
  "enable_jimaku": true,
  "enable_viability_check": true
}
```

- `enable_jimaku`: When true, the app will attempt to fetch Japanese subs via the Jimaku API. Requires `JIMAKU_API_KEY` in your environment.
- `enable_viability_check`: When true, MPV is monitored for 20 seconds after launch. If no viable playback is detected, the process is terminated and the next server is tried. When false, MPV takes over and is not killed after 20 seconds.

## Troubleshooting
- Jimaku API issues: Get your key from jimaku.cc and add it to environment variables (e.g. JIMAKU_API_KEY=yourkey) or paste directly in the code.
- MPV not launching? Ensure it's in your PATH. Test with `mpv --version`
- If subtitle are not converting. Ensure FFmpeg in your PATH. Test with `ffmpeg -version` or if it's not installed, install first.
- yt-dlp not detected? Run `yt-dlp --version` to check. If not found, make sure the folder containing `yt-dlp.exe` is in your PATH (you can also put it in the same folder as MPV).
- Stream plays but gets killed with a viability timeout (e.g. "Timed out. Terminating hung process."): set `"enable_viability_check": false` in `config.json` to let MPV keep control and avoid the 20 second kill.
  
## Contributing
Pull requests welcome! Fork the repo, create a branch, and submit.

## License
This project is licensed under the MIT License - see the [LICENSE](https://github.com/dhilzyi/hianime-with-local-mpv/blob/master/LICENSE) file for details.

