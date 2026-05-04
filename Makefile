PYTHON ?= python
PIP ?= $(PYTHON) -m pip
ADULT_FLAG ?= adult-flag

MEDIA_DIR ?=
DOWNLOAD_DIR ?= ./downloaded-media
DB ?= media_flags.sqlite
EXPORT ?= media_flags.jsonl
PREFIX ?= twitter-media
RESULTS_PREFIX ?= twitter-results
STATE_DB ?= .adult-flag-r2-upload-$(subst /,_,$(PREFIX)).sqlite
LLAVA ?= review
WORKERS ?= 4

.PHONY: help install install-dev install-all test config-check scan process export r2-upload-dry-run r2-upload r2-download

help:
	@echo "Targets:"
	@echo "  make install              Install package editable"
	@echo "  make install-dev          Install package with dev deps"
	@echo "  make install-all          Install package with ml/r2/dev deps"
	@echo "  make test                 Run pytest"
	@echo "  make config-check         Show masked config"
	@echo "  make scan MEDIA_DIR=...   Scan media into SQLite"
	@echo "  make process              Process scanned media"
	@echo "  make export               Export JSONL results"
	@echo "  make r2-upload-dry-run MEDIA_DIR=..."
	@echo "  make r2-upload MEDIA_DIR=..."
	@echo "  make r2-download DOWNLOAD_DIR=..."

install:
	$(PIP) install -U pip
	$(PIP) install -e .

install-dev:
	$(PIP) install -U pip
	$(PIP) install -e '.[dev]'

install-all:
	$(PIP) install -U pip
	$(PIP) install -e '.[ml,r2,dev]'

test:
	$(PYTHON) -m pytest -q

config-check:
	$(ADULT_FLAG) config-check

scan:
	@test -n "$(MEDIA_DIR)" || (echo "Set MEDIA_DIR=/path/to/media" && exit 2)
	$(ADULT_FLAG) --db "$(DB)" scan "$(MEDIA_DIR)"

process:
	$(ADULT_FLAG) --db "$(DB)" process --llava "$(LLAVA)"

export:
	$(ADULT_FLAG) --db "$(DB)" export "$(EXPORT)"

r2-upload-dry-run:
	@test -n "$(MEDIA_DIR)" || (echo "Set MEDIA_DIR=/path/to/media" && exit 2)
	$(ADULT_FLAG) r2-upload "$(MEDIA_DIR)" --prefix "$(PREFIX)" --state-db "$(STATE_DB)" --workers "$(WORKERS)" --dry-run

r2-upload:
	@test -n "$(MEDIA_DIR)" || (echo "Set MEDIA_DIR=/path/to/media" && exit 2)
	$(ADULT_FLAG) r2-upload "$(MEDIA_DIR)" --prefix "$(PREFIX)" --state-db "$(STATE_DB)" --workers "$(WORKERS)"

r2-download:
	$(ADULT_FLAG) r2-download "$(DOWNLOAD_DIR)" --prefix "$(PREFIX)"
