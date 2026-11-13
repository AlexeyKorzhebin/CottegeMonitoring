"""Exercise packaging preflight with fake git/docker; never invoke real Docker."""
import os
from pathlib import Path
import subprocess

SCRIPT = Path(__file__).resolve().parents[2] / 'deploy/platform-metrics/prepare-build.sh'
BASE = 'sha256:cc3c918041ea047ea924eee60eba1c0789235950df84606ee8aa89249d04b8a9'


def run_script(tmp_path, mode, endpoint='desktop-linux', dirty=False):
    bindir = tmp_path / 'bin'
    bindir.mkdir()
    log = tmp_path / 'docker.log'
    (bindir / 'git').write_text('''#!/bin/sh
case " $* " in
  *" rev-parse "*) printf '/fake/repo\\n' ;;
  *" status "*) [ "$DIRTY" = 0 ] || printf ' M file\\n' ;;
esac
exit 0
''')
    (bindir / 'docker').write_text('''#!/bin/sh
printf '%s\\n' "$*" >> "$LOG"
if [ "$*" = 'context show' ]; then echo desktop-linux; exit; fi
[ "$1" = --context ] && [ "$2" = desktop-linux ] || exit 10
shift 2
case "$1 $2" in
  'context inspect') echo unix:///desktop.sock ;;
  'buildx inspect') [ "$3" = desktop-linux ] || exit 11
    printf 'Driver: docker\\nNodes:\\nName: desktop-linux\\nEndpoint: %s\\nPlatforms: linux/amd64, linux/arm64\\n' "$ENDPOINT" ;;
  'buildx build') [ "$3" = --builder ] && [ "$4" = desktop-linux ] || exit 12 ;;
  'image tag') touch "$TAGGED" ;;
  'image inspect')
    case "$3" in
      sha256:*) case "$5" in *Architecture*) echo linux/amd64 ;; *) echo "$BASE" ;; esac ;;
      platform-metrics-base:*) [ -f "$TAGGED" ] || exit 1; [ "$#" = 3 ] || echo "$BASE" ;;
      *) exit 1 ;;
    esac ;;
  *) exit 13 ;;
esac
''')
    for file in bindir.iterdir():
        file.chmod(0o755)
    env = dict(os.environ, PATH=f'{bindir}:{os.environ["PATH"]}', LOG=str(log),
               TAGGED=str(tmp_path / 'tagged'), BASE=BASE, ENDPOINT=endpoint,
               DIRTY='1' if dirty else '0')
    result = subprocess.run(['sh', str(SCRIPT), mode], env=env, capture_output=True, text=True)
    return result, log.read_text().splitlines() if log.exists() else []


def test_build_pins_all_commands_to_selected_context(tmp_path):
    result, calls = run_script(tmp_path, '--build')
    assert result.returncode == 0, result.stderr
    assert calls[0] == 'context show'
    assert all(call.startswith('--context desktop-linux ') for call in calls[1:])
    assert any('buildx build --builder desktop-linux --platform linux/amd64 --pull=false --load' in call for call in calls)
    assert any('image tag ' in call for call in calls)


def test_mismatched_or_ambiguous_endpoint_refuses_before_writes(tmp_path):
    for index, endpoint in enumerate(('default', 'desktop-linux\nEndpoint: other')):
        case = tmp_path / str(index)
        case.mkdir()
        result, calls = run_script(case, '--build', endpoint)
        assert result.returncode != 0
        assert 'does not uniquely match' in result.stderr
        assert not any('image tag ' in call or 'buildx build ' in call for call in calls)


def test_dirty_checkout_refuses_before_docker(tmp_path):
    result, calls = run_script(tmp_path, '--build', dirty=True)
    assert result.returncode != 0
    assert 'Checkout is dirty' in result.stderr
    assert calls == []
