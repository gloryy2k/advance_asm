PYTHON ?= python
TARGET ?= example.com
DEPTH ?= passive

.PHONY: test frontend smoke
test:
	$(PYTHON) -m pytest -m "not integration"
frontend:
	cd frontend && npm ci && npm test && npm run build
smoke:
	$(PYTHON) scripts/smoke.py --target "$(TARGET)" --depth "$(DEPTH)"
