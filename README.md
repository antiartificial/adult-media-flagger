# Adult Media Flagger

Local-first adult-content flagging for image/video archives. This is designed for media downloaded from X/Twitter tooling such as field-theory's CLI, where the first goal is to identify likely adult media before doing richer description/search work later.

The current pipeline is:

```text
scan files -> hash + metadata ledger -> adult classifier -> optional LLaVA review -> JSONL export
```

## What it does

- Scans images and videos into a resumable SQLite database.
- Computes SHA-256 hashes for dedupe/auditing.
- Preserves nearby JSON sidecar metadata when present.
- Runs `opennsfw2` as the fast numeric adult classifier.
- Samples video frames with `ffmpeg`/`ffprobe` and scores the frames.
- Optionally sends review/flagged items to Ollama LLaVA for a structured second opinion.
- Exports results as JSONL.

## Install on macOS with fish + virtualfish

From your workspace:

```fish
cd /Users/arti/Desktop/Claude/adult-media-flagger

# Create and activate a virtualfish environment.
vf new adult-media-flagger

# Install the package in editable mode.
python -m pip install -U pip
python -m pip install -e '.[dev]'
```

The Mac can do scanning/export without ML dependencies. If you want to test the classifier on the Mac too:

```fish
python -m pip install -e '.[ml,dev]'
```

If you also want the built-in R2 upload/download commands:

```fish
python -m pip install -e '.[r2,dev]'
```

## Install on Linux processing box

```fish
cd /path/to/adult-media-flagger
vf new adult-media-flagger
python -m pip install -U pip
python -m pip install -e '.[ml,dev]'
```

For Linux processing with R2 support:

```fish
python -m pip install -e '.[ml,r2,dev]'
```

Install FFmpeg for video support:

```fish
# Ubuntu/Debian
sudo apt install ffmpeg
```

Install and run Ollama if you want the LLaVA pass:

```fish
ollama pull llava:13b
ollama serve
```

If the Ollama server is already managed by your desktop environment or systemd, you do not need to run `ollama serve` manually.

## Basic CLI

Scan a downloaded media folder:

```fish
adult-flag --db media_flags.sqlite scan /path/to/twitter-media
```

Process unprocessed files with the default thresholds and LLaVA review pass:

```fish
adult-flag --db media_flags.sqlite process
```

Run classifier only, no LLaVA:

```fish
adult-flag --db media_flags.sqlite process --llava off
```

Only process 100 files for a smoke test:

```fish
adult-flag --db media_flags.sqlite process --limit 100 --llava off
```

Review both `review` and `adult_likely` items with LLaVA:

```fish
adult-flag --db media_flags.sqlite process --llava flagged --llava-model llava:13b
```

Export everything to JSONL:

```fish
adult-flag --db media_flags.sqlite export media_flags.jsonl
```

## Decisions

By default, classifier scores are bucketed as:

```text
safe           score < 0.35
review         0.35 <= score < 0.80
adult_likely   score >= 0.80
```

Tune these per run:

```fish
adult-flag --db media_flags.sqlite process --safe-max 0.25 --adult-min 0.75
```

The exported JSONL includes both the classifier decision and `final_decision`. When LLaVA is enabled, `final_decision` may be adjusted based on its structured review.

## R2 workflow

R2 is not required for the local classifier, but the CLI includes simple upload/download commands using the S3-compatible API.

### Obtain R2 credentials

R2 needs to be enabled for the Cloudflare account before keys can be created. In the Cloudflare dashboard:

1. Open **R2 Object Storage**.
2. Enable R2 if prompted.
3. Create a bucket, for example `adult-media-flagger`.
4. Open **Manage R2 API Tokens**.
5. Create an API token with **Object Read & Write** access for the bucket.
6. Copy the generated access key ID and secret access key. The secret is only shown once.

### Configure `.env`

Copy the template:

```fish
cp .env.example .env
```

Edit `.env`:

```dotenv
R2_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
AWS_ACCESS_KEY_ID=<r2-access-key-id>
AWS_SECRET_ACCESS_KEY=<r2-secret-access-key>
AWS_SESSION_TOKEN=
ADULT_FLAG_R2_BUCKET=adult-media-flagger
ADULT_FLAG_R2_MEDIA_PREFIX=twitter-media
ADULT_FLAG_R2_RESULTS_PREFIX=twitter-results
OLLAMA_ENDPOINT=http://localhost:11434/api/generate
OLLAMA_MODEL=llava:13b
```

Check the project sees the config without printing secrets:

```fish
adult-flag config-check
```

You can still set credentials directly in fish instead:

```fish
set -gx R2_ENDPOINT_URL 'https://<account-id>.r2.cloudflarestorage.com'
set -gx AWS_ACCESS_KEY_ID '<r2-access-key-id>'
set -gx AWS_SECRET_ACCESS_KEY '<r2-secret-access-key>'
```

Upload from the Mac:

```fish
adult-flag r2-upload /path/to/twitter-media --bucket my-media-bucket --prefix twitter-media
```

Download on the Linux box:

```fish
adult-flag r2-download /data/twitter-media --bucket my-media-bucket --prefix twitter-media
```

Then process locally:

```fish
adult-flag --db /data/media_flags.sqlite scan /data/twitter-media
adult-flag --db /data/media_flags.sqlite process --llava review
adult-flag --db /data/media_flags.sqlite export /data/media_flags.jsonl
```

Upload results back:

```fish
mkdir -p /data/media-results
cp /data/media_flags.sqlite /data/media_flags.jsonl /data/media-results/
adult-flag r2-upload /data/media-results --bucket my-media-bucket --prefix twitter-results
```

A clean split is:

```text
Mac: scan/download media -> upload media + SQLite/JSONL manifest to R2
Linux: sync from R2 -> process -> export results -> upload results back to R2
Mac: sync results down
```

For very large archives, `rclone` is still worth considering because it has mature retry, checksum, and progress behavior.

## Uploading field-theory media to R2

Once `.env` is configured, upload the downloaded media folder from the Mac:

```fish
adult-flag r2-upload /path/to/field-theory-media --prefix twitter-media
```

On the Linux processing box:

```fish
adult-flag r2-download /data/twitter-media --prefix twitter-media
adult-flag --db /data/media_flags.sqlite scan /data/twitter-media
adult-flag --db /data/media_flags.sqlite process --llava review
adult-flag --db /data/media_flags.sqlite export /data/media_flags.jsonl
```

Then upload only the processing outputs back:

```fish
mkdir -p /data/media-results
cp /data/media_flags.sqlite /data/media_flags.jsonl /data/media-results/
adult-flag r2-upload /data/media-results --prefix twitter-results
```

Do not commit downloaded media, `.env`, SQLite databases, or JSONL exports to git.

## Public repository safety

This repository is safe to publish when `.gitignore` is respected. The real `.env` file is ignored, and [.env.example](.env.example) contains only blank placeholders. Before pushing publicly, run:

```fish
git status --short --ignored
adult-flag config-check
```

`config-check` masks secrets and should never print full credentials.

## Development

Run tests:

```fish
pytest
```

The code intentionally imports `opennsfw2` only when `adult-flag process` runs, so scan/export commands remain usable on machines without the ML stack installed.
