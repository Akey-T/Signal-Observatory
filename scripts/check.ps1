$ErrorActionPreference = 'Stop'

$python = if (Test-Path '.venv\Scripts\python.exe') {
    '.venv\Scripts\python.exe'
} else {
    'python'
}

& $python -m ruff check .
& $python -m ruff format --check .
& $python -m mypy apps packages config db
& $python -m pytest
npm run lint
npm run format:check
npm run typecheck
npm run test
npm run build
