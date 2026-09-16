if [ -f "${HOME}/.bashrc" ]; then
  . "${HOME}/.bashrc"
fi
_pd_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -f "${_pd_root}/.venv/bin/activate" ]; then
  . "${_pd_root}/.venv/bin/activate"
fi
unset _pd_root
