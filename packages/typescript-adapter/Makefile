.DEFAULT_GOAL := verify
NPM ?= npm

.PHONY: install verify build test pack
install:
	$(NPM) ci --ignore-scripts
verify:
	$(NPM) run verify
build:
	$(NPM) run build
test:
	$(NPM) test
pack: verify
	$(NPM) run test:pack
	$(NPM) pack --ignore-scripts
