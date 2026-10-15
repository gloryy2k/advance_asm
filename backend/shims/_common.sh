# Sourced by the BBASM shims. Not executable on its own.
# Records how one external data source behaved so the dashboard can say which one failed, never what it returned.
bbasm_shim_dir() { cd "$(dirname "${BASH_SOURCE[1]}")" && pwd; }

# The engine re-exports PATH with ~/go/bin and /usr/local/bin in front, which would hide a PATH shim, so BBASM also
# exports these wrappers as bash functions (they win over any PATH lookup). Inside a wrapper the function itself
# must not be found again: use `type -P` (files on PATH only) and an absolute path.
unset -f curl subfinder 2>/dev/null

bbasm_real() {  # $1 = tool name, $2 = shim dir: first executable on PATH that is not the shim itself
    local clean="" part parts
    IFS=: read -ra parts <<<"$PATH"
    for part in "${parts[@]}"; do [ "$part" = "$2" ] || clean="$clean:$part"; done
    PATH="${clean#:}" type -P "$1"
}

bbasm_record() {  # $1 source label, $2 status (ok|timeout|error), $3 seconds, $4 exit code
    [ -n "${RECON_OUT_DIR:-}" ] && [ -d "$RECON_OUT_DIR" ] || return 0
    printf '%s\t%s\t%s\t%s\n' "$1" "$2" "$3" "$4" >> "$RECON_OUT_DIR/.source_status.tsv" 2>/dev/null || true
}
