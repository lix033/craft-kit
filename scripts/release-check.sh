#!/bin/sh
# Builds both packages and checks them, publishing nothing. Run from anywhere: sh scripts/release-check.sh
set -eu
export PIP_DISABLE_PIP_VERSION_CHECK=1
cd "$(dirname "$0")/.."
py=$(sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml)
js=$(node -p 'require("./package.json").version')
mod=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' craft_kit/__init__.py)
if [ "$py" != "$js" ] || [ "$py" != "$mod" ]; then
  echo "✗ versions differ: pyproject $py, package.json $js, __init__ $mod" >&2; exit 1
fi
echo "● version $py"
rm -rf dist build ./*.egg-info craft_kit/__pycache__
for f in craft_kit/*.py; do python3 -m py_compile "$f"; done
node --check bin/launch.js
uv build -q
uvx -q twine check --strict dist/*
mkdir -p dist/npm
tgz=dist/npm/$(npm pack -q --pack-destination dist/npm | tail -1)
tmp=$(mktemp -d)
python3 -m venv "$tmp/venv" && "$tmp/venv/bin/pip" install -q dist/craftkit-"$py"-py3-none-any.whl
[ "$("$tmp/venv/bin/craft" --version)" = "craft $py" ]
npm install -g -q --prefix "$tmp/npm" "$tgz" >/dev/null
[ "$("$tmp/npm/bin/craft" --version)" = "craft $py" ]
[ "$("$tmp/npm/bin/craftkit" --version)" = "craft $py" ]
rm -rf "$tmp" build ./*.egg-info
echo "✓ ready to publish: dist/craftkit-$py.tar.gz, dist/craftkit-$py-py3-none-any.whl, $tgz"
