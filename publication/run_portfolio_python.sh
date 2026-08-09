#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(/usr/bin/dirname -- "$0")" && pwd -P)
PROJECT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd -P)

strict_portfolio_git() {
    /usr/bin/env -i \
        HOME=/nonexistent-corelm-portfolio-launcher \
        PATH=/usr/bin:/bin:/usr/sbin:/sbin \
        LANG=C \
        LC_ALL=C \
        GIT_CONFIG_GLOBAL=/dev/null \
        GIT_CONFIG_NOSYSTEM=1 \
        GIT_NO_REPLACE_OBJECTS=1 \
        GIT_OPTIONAL_LOCKS=0 \
        GIT_TERMINAL_PROMPT=0 \
        /usr/bin/git \
            -c core.fsmonitor=false \
            -c core.untrackedCache=false \
            -c core.trustctime=true \
            -c core.checkStat=default \
            -c core.hooksPath=/dev/null \
            -C "$PROJECT_DIR" "$@"
}

strict_portfolio_source_bootstrap() {
    [ "$(strict_portfolio_git rev-parse --is-inside-work-tree)" = true ] || {
        printf '%s\n' 'portfolio launcher requires an exact Git checkout' >&2
        return 1
    }
    [ -z "$(strict_portfolio_git for-each-ref --format='%(refname)' refs/replace)" ] || {
        printf '%s\n' 'portfolio launcher forbids Git replacement refs' >&2
        return 1
    }
    graft_path=$(strict_portfolio_git rev-parse --git-path info/grafts)
    case "$graft_path" in
        /*) ;;
        *) graft_path="$PROJECT_DIR/$graft_path" ;;
    esac
    [ ! -e "$graft_path" ] || {
        printf '%s\n' 'portfolio launcher forbids legacy Git grafts' >&2
        return 1
    }
    for sparse_key in core.sparseCheckout core.sparseCheckoutCone index.sparse; do
        sparse_value=$(strict_portfolio_git config --bool "$sparse_key" 2>/dev/null || :)
        [ -z "$sparse_value" ] || [ "$sparse_value" = false ] || {
            printf '%s\n' 'portfolio launcher forbids sparse Git state' >&2
            return 1
        }
    done
    for flag_view in -t -v -f; do
        flag_rows=$(strict_portfolio_git ls-files "$flag_view") || return 1
        if [ -n "$flag_rows" ] && \
            printf '%s\n' "$flag_rows" | /usr/bin/grep -qv '^H '; then
            printf '%s\n' 'portfolio launcher forbids hidden Git index flags' >&2
            return 1
        fi
    done
    strict_portfolio_git diff-index --cached --quiet HEAD -- || {
        printf '%s\n' 'portfolio launcher index differs from signed HEAD' >&2
        return 1
    }
    strict_portfolio_git diff-files --quiet --ignore-submodules=none -- || {
        printf '%s\n' 'portfolio launcher tracked bytes differ from signed HEAD' >&2
        return 1
    }
    [ -z "$(strict_portfolio_git status --porcelain=v1 \
        --untracked-files=all --ignored=no --ignore-submodules=none)" ] || {
        printf '%s\n' 'portfolio launcher forbids untracked source files' >&2
        return 1
    }
    ignored_source=$(strict_portfolio_git ls-files \
        --others --ignored --exclude-standard -- \
        . ':(exclude)dist/CoreLMBenchmark.app/**') || return 1
    [ -z "$ignored_source" ] || {
        printf '%s\n' \
            'portfolio launcher forbids ignored paths outside the verified app bundle' >&2
        return 1
    }
}

usage() {
    printf '%s\n' \
        'usage: run_portfolio_python.sh ABSOLUTE_PYTHON TOOL.py [arguments...]' >&2
}

[ "$#" -ge 2 ] || {
    usage
    exit 2
}

portfolio_python=$1
portfolio_tool=$2
shift 2

case "$portfolio_python" in
    /*) ;;
    *)
        printf '%s\n' 'portfolio Python must be an absolute executable path' >&2
        exit 2
        ;;
esac
[ -x "$portfolio_python" ] || {
    printf '%s\n' 'portfolio Python executable is unavailable' >&2
    exit 2
}

case "$portfolio_tool" in
    build_portfolio_release.py|collect_portfolio_demo.py|verify_portfolio_github_release.py) ;;
    *)
        printf '%s\n' 'portfolio Python tool is not allowlisted' >&2
        exit 2
        ;;
esac

portfolio_help=0
case "${1:-}" in
    -h|--help) portfolio_help=1 ;;
esac

portfolio_tmp_root=${TMPDIR:-/tmp}
case "$portfolio_tmp_root" in
    /*) ;;
    *)
        printf '%s\n' 'portfolio TMPDIR must be an absolute directory' >&2
        exit 2
        ;;
esac
portfolio_tmp_root=$(CDPATH= cd -- "$portfolio_tmp_root" && pwd -P) || {
    printf '%s\n' 'portfolio TMPDIR is unavailable' >&2
    exit 2
}
case "$portfolio_tmp_root/" in
    "$PROJECT_DIR/"|"$PROJECT_DIR/"*)
        printf '%s\n' \
            'portfolio Python cache must be outside the source checkout' >&2
        exit 2
        ;;
esac

if [ "$portfolio_help" -eq 1 ]; then
    printf 'usage: %s [arguments...]\n' "$portfolio_tool"
    exit 0
fi

strict_portfolio_source_bootstrap

portfolio_pycache=$(/usr/bin/mktemp -d \
    "$portfolio_tmp_root/corelm-portfolio-pycache.XXXXXX")
/bin/chmod 700 "$portfolio_pycache"
portfolio_status=0
TMPDIR="$portfolio_tmp_root" \
"$portfolio_python" -I -B -X "pycache_prefix=$portfolio_pycache" \
    "$SCRIPT_DIR/$portfolio_tool" "$@" || portfolio_status=$?
if ! /bin/rmdir "$portfolio_pycache"; then
    printf '%s\n' \
        'portfolio Python cache boundary was not empty after execution' >&2
    exit 1
fi
exit "$portfolio_status"
