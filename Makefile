PY := .venv/Scripts/python.exe
PRE_COMMIT := .venv/Scripts/pre-commit.exe

.PHONY: help setup run poc lint build install-config clean

help: ## Show available commands
	@echo setup........... Create venv, install deps, install pre-commit hook
	@echo run............. Run the app from source
	@echo poc............. Run the SMTC multi-pause throwaway prototype
	@echo lint............ Run all pre-commit hooks
	@echo build........... Build CS2MediaControl.exe
	@echo install-config.. Copy the GSI config into the CS2 cfg folder
	@echo clean........... Remove build artifacts and bytecode caches

setup: ## Create venv, install deps, and install pre-commit hook
	if not exist .venv\Scripts\python.exe python -m venv .venv
	$(PY) -m pip install -r requirements.txt -r requirements-dev.txt
	$(PRE_COMMIT) install

run: ## Run the app from source
	$(PY) cs2_media_control.py

poc: ## Run the SMTC multi-pause throwaway prototype
	$(PY) poc/poc_smtc_pause.py

lint: ## Run all pre-commit hooks (ruff, ruff-format, mdformat, hygiene)
	$(PRE_COMMIT) run --all-files

build: ## Build CS2MediaControl.exe via the PowerShell script
	powershell -NoProfile -ExecutionPolicy Bypass -File build_exe.ps1

install-config: ## Copy the GSI config into the CS2 cfg folder
	powershell -NoProfile -ExecutionPolicy Bypass -File install_config.ps1

clean: ## Remove build artifacts and bytecode caches
	-rmdir /s /q build dist __pycache__ poc\__pycache__
	-del CS2MediaControl.spec
