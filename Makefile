BLENDER        ?= /Applications/Blender.app/Contents/MacOS/Blender
BLENDER_VER    ?= 5.1
EXTENSIONS_DIR := $(HOME)/Library/Application Support/Blender/$(BLENDER_VER)/extensions/user_default
ADDON          := blender_keymap_helper
BUILD_DIR      := /tmp/blender-keymap-helper-build
DIST_DIR       := dist
VERSION        := $(shell python3 -c "\
import re, pathlib; \
src = pathlib.Path('$(ADDON)/__init__.py').read_text(); \
m = re.search(r'\"version\":\s*\((\d+),\s*(\d+),\s*(\d+)\)', src); \
print(f'{m.group(1)}.{m.group(2)}.{m.group(3)}') if m else print('0.0.0')")
DIST_ZIP       := $(DIST_DIR)/$(ADDON)-$(VERSION).zip

.PHONY: install uninstall blender dist

dist:
	@mkdir -p "$(DIST_DIR)"
	@rm -f "$(DIST_ZIP)"
	@cd "$(CURDIR)" && \
		find "$(ADDON)" \
			\( -name "__pycache__" -o -name "*.pyc" -o -name "*.pyo" -o -name "scripts" \) -prune \
			-o -type f -print \
		| zip -q "$(DIST_ZIP)" -@
	@echo "$(DIST_ZIP)"

dev:
	@mkdir -p "$(BUILD_DIR)"
	$(BLENDER) --command extension build --source-dir "$(CURDIR)/$(ADDON)" --output-dir "$(BUILD_DIR)"
	$(BLENDER) --command extension install-file "$(BUILD_DIR)/$(ADDON)-"*.zip --repo user_default --enable
	@rm -rf "$(EXTENSIONS_DIR)/$(ADDON)"
	@ln -sf "$(CURDIR)/$(ADDON)" "$(EXTENSIONS_DIR)/$(ADDON)"
	@echo "Installed and linked $(ADDON) for live development"

uninstall:
	$(BLENDER) --command extension remove "$(ADDON)" --repo user_default 2>/dev/null || true
	@rm -f "$(EXTENSIONS_DIR)/$(ADDON)"
	@echo "Removed $(ADDON)"

blender:
	$(BLENDER)

