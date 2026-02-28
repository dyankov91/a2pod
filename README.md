# A2Pod 🎧

Convert any article URL into an audiobook on Apple Silicon. Generates audio locally, uploads to S3, and publishes a podcast feed you can subscribe to in Apple Podcasts on your iPhone.

## Features

- **Any URL** — articles, blog posts, newsletters, X/Twitter posts and articles
- **Text cleaning** — automatically strips URLs, markdown, code blocks, CTAs, and web artifacts before TTS
- **Episode summaries** — generates 2-3 sentence descriptions via Ollama (optional, graceful fallback)
- **Apple Silicon TTS** — Kokoro model via MLX, fast and natural-sounding
- **Podcast feed** — uploads to S3 and updates an RSS feed, subscribe once in Apple Podcasts
- **Telegram bot** — send a URL to your bot, get audio back in chat with live progress updates
- **Offline fallback** — works without AWS, just saves M4B files locally

## Requirements

- macOS with Apple Silicon (M1/M2/M3/M4)
- Python 3.10+
- ~500MB disk for model + dependencies
- X API bearer token (optional, for X/Twitter posts)
- AWS account (optional, for podcast sync)
- [Ollama](https://ollama.com) (optional, for episode summaries)

## Quick Start

```bash
git clone https://github.com/dyankov91/a2pod.git
cd a2pod
./install.sh
```

The installer handles: dependencies, model download, PATH setup, and optional AWS / Telegram bot configuration.

Then:

```bash
a2pod https://example.com/some-article
```

## Usage

```bash
# Basic — converts and uploads to podcast feed
a2pod https://example.com/article

# Custom voice (male)
a2pod https://example.com/article --voice am_michael

# Faster speech
a2pod https://example.com/article --speed 1.2

# From a local text file
a2pod --file article.txt --title "My Article"

# Local only, skip S3 upload
a2pod https://example.com/article --no-upload

# Custom output path
a2pod https://example.com/article --output ~/Desktop/article.m4b

# Skip summary generation
a2pod https://example.com/article --no-summary

# Use a different Ollama model for summaries
a2pod https://example.com/article --model mistral
```

### X/Twitter

Works with posts and long-form articles:

```bash
a2pod https://x.com/someuser/status/1234567890
```

Requires an X API bearer token. Add it to `~/.config/a2pod/config`:

```ini
[x]
bearer_token = YOUR_TOKEN_HERE
```

The installer can also set this up for you during `./install.sh`.

## Telegram Bot

Send article URLs to a Telegram bot and receive the audio file directly in chat. The bot shows live progress as each pipeline step runs.

### Setup

The installer can configure this for you during `./install.sh`. To set up manually:

1. Message [@BotFather](https://t.me/BotFather) on Telegram and create a new bot
2. Get your numeric user ID by messaging [@userinfobot](https://t.me/userinfobot)
3. Add to `~/.config/a2pod/config`:

```ini
[telegram]
bot_token = 7123456789:AAH...
allowed_users = 123456789,987654321
```

Multiple user IDs can be comma-separated. Only listed users can interact with the bot.

### Running as a Background Service

The installer offers to set up a launchd service that starts the bot automatically whenever your Mac is on and restarts it if it crashes.

To install the service manually:

```bash
# Create the launchd plist (adjust paths to match your setup)
cat > ~/Library/LaunchAgents/com.a2pod.bot.plist <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.a2pod.bot</string>
    <key>ProgramArguments</key>
    <array>
        <string>$(python3 -c 'import sys; print(sys.executable)')</string>
        <string>/path/to/a2pod/bin/a2pod-bot</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/path/to/a2pod</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONPATH</key>
        <string>/path/to/a2pod/lib</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>~/.config/a2pod/bot.log</string>
    <key>StandardErrorPath</key>
    <string>~/.config/a2pod/bot.log</string>
</dict>
</plist>
EOF

# Load the service
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.a2pod.bot.plist
```

### Managing the Service

```bash
# Check status
launchctl print gui/$(id -u)/com.a2pod.bot

# Restart
launchctl kickstart -k gui/$(id -u)/com.a2pod.bot

# Stop
launchctl bootout gui/$(id -u)/com.a2pod.bot

# View logs
tail -f ~/.config/a2pod/bot.log
```

### Running Manually

```bash
a2pod-bot
```

## Episode Summaries

Summaries are generated automatically via a local Ollama model and added to the podcast feed as episode descriptions (visible in Apple Podcasts).

To set up:

```bash
# Install Ollama
brew install ollama

# Pull a model (default: llama3.2)
ollama pull llama3.2
```

If Ollama isn't running, a fallback summary (first sentence of the article) is used instead. Use `--no-summary` to skip entirely, or `--model <name>` to use a different model.

## Podcast Setup

When AWS is configured, each audiobook is uploaded to S3 and the podcast feed is updated automatically. Subscribe once in Apple Podcasts:

1. Open **Apple Podcasts** on your iPhone
2. Tap **Search** → tap the search bar
3. Paste the feed URL:
   ```
   https://my-podcast-feed.s3.eu-central-1.amazonaws.com/feed.xml
   ```
4. Tap **Follow**

Every new article you convert will appear as an episode.

### AWS Setup

The installer prompts for AWS credentials. To configure manually:

```bash
aws configure --profile default
# Region: eu-central-1
```

The S3 bucket (`my-podcast-feed`) needs public read access for Apple Podcasts to fetch the feed and audio files.

## Available Voices

| Voice | Gender | ID |
|-------|--------|----|
| Heart (default) | Female | `af_heart` |
| Bella | Female | `af_bella` |
| Nicole | Female | `af_nicole` |
| Sarah | Female | `af_sarah` |
| Sky | Female | `af_sky` |
| Adam | Male | `am_adam` |
| Michael | Male | `am_michael` |

## How It Works

```
URL → Scrape → Clean → Summarize → Chunk → TTS → M4A → S3 → Podcast Feed
```

1. **Scrape** — trafilatura extracts article text; X API v2 handles X/Twitter posts
2. **Clean** — regex strips URLs, markdown, code blocks, CTAs, and web artifacts
3. **Summarize** — Ollama generates a 2-3 sentence episode description (optional)
4. **Chunk** — splits into ~2000 char segments at sentence boundaries
5. **TTS** — Kokoro-82M generates audio locally on Apple Silicon
6. **Assemble** — ffmpeg concatenates chunks into M4A with metadata
7. **Publish** — uploads to S3 and updates the podcast RSS feed

## File Structure

```
a2pod/
├── install.sh              # One-time setup (deps, model, AWS, Telegram)
├── bin/
│   ├── a2pod       # Main CLI
│   └── a2pod-bot   # Telegram bot entry point
├── lib/
│   ├── errors.py           # Shared PipelineError exception
│   ├── pipeline.py         # Orchestration (used by CLI and bot)
│   ├── extractor.py        # URL/file text extraction
│   ├── cleaner.py          # Regex + LLM text cleaning for audio
│   ├── summarizer.py       # Ollama episode summaries
│   ├── chunker.py          # Text splitting
│   ├── tts.py              # MLX Audio TTS wrapper
│   ├── assembler.py        # Audio concat + M4A packaging
│   ├── publisher.py        # S3 upload + podcast RSS feed
│   └── telegram_bot.py     # Telegram bot handlers + polling
└── README.md
```

## Output

- Audiobooks saved to `~/A2Pod/`
- Uploaded to `s3://my-podcast-feed/audiobooks/`
- Feed at `https://my-podcast-feed.s3.eu-central-1.amazonaws.com/feed.xml`

## License

MIT
