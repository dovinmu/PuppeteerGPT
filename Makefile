.DEFAULT_GOAL := help

.PHONY: help validate test smoke

help:
	@printf '%s\n' \
	  'validate  Validate the versioned benchmark suite' \
	  'test      Run the standard-library unit tests' \
	  'smoke     Run the offline engine smoke scenario'

validate:
	uv run puppeteergpt validate --suite benchmark/suites/v4-flash.json

test:
	uv run python -m unittest discover -s tests -v

smoke:
	uv run puppeteergpt smoke --offline --output /tmp/puppeteergpt-smoke
