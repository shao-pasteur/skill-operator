#!/bin/sh
# Run one of the sharron scripts with Python 3.11 or newer.
#
#   sh <skill>/scripts/run.sh <script>.py [args...]
#
# Only shell builtins are used, so the launcher still works when PATH holds nothing but interpreters.

script=${1-}
case $script in
  config.py|memory_guard.py|finance.py|refcheck.py|trace.py|detect_stack.py|datasync.py) ;;
  *)
    printf "run.sh: unknown script '%s'\n" "$script" >&2
    exit 2
    ;;
esac
shift

case $0 in */*) dir=${0%/*} ;; *) dir=. ;; esac

for py in python3.14 python3.13 python3.12 python3.11 python3 python; do
  if command -v "$py" >/dev/null 2>&1 &&
    "$py" -c 'import sys; sys.exit(sys.version_info < (3, 11))' >/dev/null 2>&1; then
    exec "$py" "$dir/$script" "$@"
  fi
done

if command -v uv >/dev/null 2>&1; then
  exec uv run --no-project --python '>=3.11' python "$dir/$script" "$@"
fi

printf '%s\n' 'sharron needs Python 3.11 or newer: install one (for example with "uv python install 3.12") and run again' >&2
exit 1
