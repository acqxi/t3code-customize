import base64
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import wsl_support as wsl  # noqa: E402


def make_runtime(path, stem='t3-0.1.12-linux-x64', extra=()):
    """A small archive shaped like upstream's Linux CLI release archive."""
    with tarfile.open(path, 'w:gz') as archive:
        def add(name, data=None, mode=0o644, kind=tarfile.REGTYPE):
            info = tarfile.TarInfo(name)
            info.type, info.mode, info.uname, info.gname, info.mtime = kind, mode, 'runner', 'runner', 1_700_000_000
            if data is None:
                archive.addfile(info)
            else:
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
        add(stem, kind=tarfile.DIRTYPE, mode=0o755)
        add(f'{stem}/t3', b'stock-executable', mode=0o755)
        add(f'{stem}/client', kind=tarfile.DIRTYPE, mode=0o755)
        add(f'{stem}/client/index.html', b'<html>stock</html>')
        add(f'{stem}/client/assets', kind=tarfile.DIRTYPE, mode=0o755)
        add(f'{stem}/client/assets/old-chunk.js', b'old')
        add(f'{stem}/node_modules', kind=tarfile.DIRTYPE, mode=0o755)
        add(f'{stem}/node_modules/node-pty/pty.node', b'\x7fELF native', mode=0o755)
        add(f'{stem}/lib/libatomic.so.1', b'\x7fELF libatomic', mode=0o644)
        for name, data in extra:
            add(name, data)


def members(path):
    found = {}
    with tarfile.open(path, 'r:gz') as archive:
        for member in archive.getmembers():
            data = archive.extractfile(member).read() if member.isfile() else None
            found[member.name] = (member.mode, data)
    return found


class RuntimeArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.stock = self.tmp / 'stock.tar.gz'
        make_runtime(self.stock)
        self.exe = self.tmp / 't3'
        self.exe.write_bytes(b'patched-executable')
        self.client = self.tmp / 'client'
        (self.client / 'assets').mkdir(parents=True)
        (self.client / 'index.html').write_text('<html>patched</html>')
        (self.client / 'assets/new-chunk.js').write_text('statsForNerds')
        (self.client / 'assets/new-chunk.js.map').write_text('{}')

    def test_replaces_executable_and_client_and_keeps_native_payload(self):
        output = self.tmp / 'out.tar.gz'
        stem, digest = wsl.rebuild_runtime_archive(self.stock, output, self.exe, self.client)
        self.assertEqual(stem, 't3-0.1.12-linux-x64')
        self.assertEqual(digest, hashlib.sha256(output.read_bytes()).hexdigest())
        after, before = members(output), members(self.stock)
        self.assertEqual(after[f'{stem}/t3'], (0o755, b'patched-executable'))
        self.assertEqual(after[f'{stem}/client/assets/new-chunk.js'][1], b'statsForNerds')
        self.assertNotIn(f'{stem}/client/assets/old-chunk.js', after)
        self.assertNotIn(f'{stem}/client/assets/new-chunk.js.map', after, 'source maps stay out like upstream')
        for name in (f'{stem}/node_modules/node-pty/pty.node', f'{stem}/lib/libatomic.so.1'):
            self.assertEqual(after[name], before[name])

    def test_output_is_reproducible(self):
        first, second = self.tmp / 'a.tar.gz', self.tmp / 'b.tar.gz'
        self.assertEqual(wsl.rebuild_runtime_archive(self.stock, first, self.exe, self.client)[1],
                         wsl.rebuild_runtime_archive(self.stock, second, self.exe, self.client)[1])

    def test_multiple_top_level_directories_rejected(self):
        bad = self.tmp / 'bad.tar.gz'
        make_runtime(bad, extra=[('other/file', b'x')])
        with self.assertRaises(wsl.WslError):
            wsl.rebuild_runtime_archive(bad, self.tmp / 'out.tar.gz', self.exe, self.client)

    def test_missing_executable_rejected(self):
        bad = self.tmp / 'bad.tar.gz'
        with tarfile.open(bad, 'w:gz') as archive:
            info = tarfile.TarInfo('t3-0.1.12-linux-x64/client/index.html')
            info.size = 1
            archive.addfile(info, io.BytesIO(b'x'))
        with self.assertRaises(wsl.WslError):
            wsl.rebuild_runtime_archive(bad, self.tmp / 'out.tar.gz', self.exe, self.client)

    def test_verification_catches_a_changed_stock_entry(self):
        output = self.tmp / 'out.tar.gz'
        wsl.rebuild_runtime_archive(self.stock, output, self.exe, self.client)
        tampered = self.tmp / 'tampered.tar.gz'
        make_runtime(tampered)
        # Same layout, but the "stock" archive now disagrees about a native entry.
        with tarfile.open(tampered, 'r:gz') as source, tarfile.open(self.tmp / 'stock2.tar.gz', 'w:gz') as target:
            for member in source.getmembers():
                data = source.extractfile(member).read() if member.isfile() else None
                if member.name.endswith('pty.node'):
                    data = b'different'
                    member.size = len(data)
                target.addfile(member, io.BytesIO(data) if data is not None else None)
        with self.assertRaises(wsl.WslError):
            wsl.verify_runtime_archive(self.tmp / 'stock2.tar.gz', output, self.exe, self.client)

    def test_hash_sidecar_matches_upstream_shape(self):
        path = self.tmp / 'wsl-runtime.tar.gz.sha256'
        wsl.write_runtime_hash(path, 'a' * 64)
        self.assertEqual(path.read_bytes(), b'a' * 64 + b'\n')


class PowerShellTests(unittest.TestCase):
    def test_single_quoted_literal(self):
        self.assertEqual(wsl.ps_string("C:\\Users\\O'Neil\\T3 Code"), "'C:\\Users\\O''Neil\\T3 Code'")

    def test_json_argument_is_not_interpolated(self):
        value = {'path': "C:\\x'; Remove-Item C:\\ -Recurse; '", 'n': 1}
        argument = wsl.ps_json_argument(value)
        self.assertNotIn('Remove-Item', argument)
        encoded = argument.split("'")[1]
        self.assertEqual(json.loads(base64.b64decode(encoded)), value)

    def test_encoded_command_is_utf16(self):
        self.assertEqual(base64.b64decode(wsl.encode_command('é')).decode('utf-16le'), 'é')

    def test_powershell_explains_disabled_interop(self):
        with tempfile.TemporaryDirectory() as folder:
            missing = str(Path(folder) / 'WSLInterop')
            with self.assertRaises(wsl.WslError) as raised:
                wsl.powershell(interop=missing)
            self.assertIn('/etc/binfmt.d/WSLInterop.conf', str(raised.exception))
            Path(missing).write_text('disabled\ninterpreter /init\n')
            self.assertFalse(wsl.interop_enabled(missing))
            Path(missing).write_text('enabled\ninterpreter /init\n')
            self.assertTrue(wsl.interop_enabled(missing))

    def test_wsl_detection(self):
        self.assertTrue(wsl.is_wsl('6.6.87.2-microsoft-standard-WSL2', interop='/nonexistent'))
        self.assertFalse(wsl.is_wsl('6.8.0-45-generic', interop='/nonexistent'))

    def test_launcher_script_falls_back_and_guards_running_instances(self):
        script = wsl.LAUNCH_PS1
        for expected in ("'disabled'", 'T3 Code was updated', 'is already running', 'T3CODE_DISABLE_AUTO_UPDATE',
                         "$env:T3CODE_UPDATE_CHECK_ONLY = 'true'",
                         'ELECTRON_RUN_AS_NODE', 'LastWriteTimeUtc.Ticks', "-ieq '-WaitPid'",
                         "$env:T3CODE_CUSTOMIZE_RELAUNCH = Join-Path $here 'launch.ps1'"):
            self.assertIn(expected, script)

    def test_robocopy_failure_codes(self):
        class Result:
            def __init__(self, code):
                self.returncode, self.stdout, self.stderr = code, '', ''
        with patch.object(wsl, 'to_windows_path', side_effect=lambda p: 'C:\\x'), \
                patch.object(wsl, 'powershell', return_value='powershell.exe'):
            with patch.object(wsl.subprocess, 'run', return_value=Result(3)):
                wsl.windows_copy_tree('/mnt/c/a', '/mnt/c/b')
            with patch.object(wsl.subprocess, 'run', return_value=Result(8)):
                with self.assertRaises(wsl.WslError):
                    wsl.windows_copy_tree('/mnt/c/a', '/mnt/c/b')


import importlib.machinery  # noqa: E402
import importlib.util  # noqa: E402

loader = importlib.machinery.SourceFileLoader('customize_wsl', str(ROOT / 't3code-customize'))
spec = importlib.util.spec_from_loader(loader.name, loader)
customize = importlib.util.module_from_spec(spec)
loader.exec_module(customize)


class WindowsFromWslToolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.local = self.tmp / 'AppData/Local'
        self.roaming = self.tmp / 'AppData/Roaming'
        self.folders = {'LOCALAPPDATA': str(self.local), 'APPDATA': str(self.roaming)}
        self.patches = [patch.object(customize, 'SYSTEM', 'linux'), patch.object(customize, 'CONFIG', self.tmp / 'config'),
                        patch.object(customize, 'HOME', self.tmp / 'home'),
                        patch.object(customize.wsl, 'is_wsl', return_value=True),
                        patch.object(customize.wsl, 'windows_folders', return_value=self.folders)]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        customize.configure(False)

    def test_configure_puts_builds_on_the_windows_drive_and_sources_on_linux(self):
        customize.configure(True)
        self.assertEqual(customize.DATA, self.local / 't3code-customize')
        self.assertEqual(customize.APP_SYSTEM, 'win32')
        self.assertEqual(customize.DESKTOP, self.roaming / customize.START_MENU)
        self.assertFalse(str(customize.SOURCE).startswith(str(self.tmp / 'AppData')))
        self.assertEqual(customize.BIN.name, 't3code-customize')
        self.assertTrue(customize.STATE.is_relative_to(customize.DATA))
        self.assertEqual(json.loads((self.tmp / 'config/config.json').read_text())['windows'], self.folders)

    def test_detects_the_windows_install_only_when_no_appimage(self):
        self.assertFalse(customize.detect_windows_target({}))
        install = self.local / 'Programs/t3code'
        install.mkdir(parents=True)
        self.assertTrue(customize.detect_windows_target({}))
        self.assertFalse(customize.detect_windows_target({'target': 'linux'}))
        self.assertTrue(customize.detect_windows_target({'app': '/mnt/c/x/T3 Code (Beta).exe'}))
        self.assertFalse(customize.detect_windows_target({'app': '/home/me/T3-Code.AppImage'}))

    def test_not_wsl_never_targets_windows(self):
        with patch.object(customize.wsl, 'is_wsl', return_value=False):
            self.assertFalse(customize.detect_windows_target({'target': 'windows'}))

    def test_fingerprint_includes_the_wsl_runtime_identity(self):
        root = self.tmp / 'app'
        (root / 'resources').mkdir(parents=True)
        (root / 'T3 Code (Beta).exe').write_bytes(b'MZ')
        (root / 'resources/app.asar').write_bytes(struct_header())
        (root / 'resources/wsl-runtime.tar.gz.sha256').write_text('a' * 64 + '\n')
        app = customize.InstalledApp.inspect(root, 'win32')
        before = customize.fingerprint(app)
        (root / 'resources/wsl-runtime.tar.gz.sha256').write_text('b' * 64 + '\n')
        self.assertNotEqual(before, customize.fingerprint(app))

    def test_required_node_reads_exact_engine_pin(self):
        with patch.object(customize, 'git', return_value='{"engines": {"node": "26.13.1"}}'):
            self.assertEqual(customize.required_node('abc'), '26.13.1')
        with patch.object(customize, 'git', return_value='{"engines": {"node": ">=24"}}'):
            self.assertIsNone(customize.required_node('abc'))


class CheckTests(unittest.TestCase):
    def test_turn_summary_reports_timing_without_content_and_skips_short_rates(self):
        turn = {'status': 'completed', 'turnTokenUsage': {'outputTokens': 1420, 'inputTokens': 47176, 'cachedInputTokens': 30787},
                'performance': {'firstTokenMs': 4236.6, 'firstTokenKind': 'reasoning', 'firstAnswerMs': 5247.1,
                                'generationMs': 9666.3, 'generationTokens': {'value': 1420, 'basis': 'provider_exact'},
                                'tools': {'count': 0, 'wallMs': 0}, 'turnMs': 14085.4, 'partial': False}}
        line = customize.turn_summary(turn)
        self.assertIn('TTFT 4.2s (reasoning)', line)
        self.assertIn('avg 147 tok/s (provider_exact)', line)
        turn['performance']['generationMs'] = 266.6
        self.assertIn('avg n/a', customize.turn_summary(turn))
        self.assertIn('[no stream timing]', customize.turn_summary({'status': 'completed'}))

    def test_runtime_processes_maps_cmdlines_to_runtime_ids(self):
        tmp = Path(tempfile.mkdtemp())
        home = tmp / 'home'
        fake_proc = tmp / 'proc'
        (fake_proc / '42').mkdir(parents=True)
        (fake_proc / '42/cmdline').write_bytes(str(home / '.t3/wsl-runtime/sha256-abc/t3').encode() + b'\0serve\0')
        real = Path
        with patch.object(customize, 'Path', side_effect=lambda p, *a: fake_proc if p == '/proc' else real(p, *a)):
            self.assertEqual(customize.runtime_processes(home), {'sha256-abc': ['42']})


def struct_header():
    import struct
    header = b'{"files":{}}'
    padded = header + b'\0' * ((-len(header)) % 4)
    pickle = struct.pack('<II', 4 + len(padded), len(header)) + padded
    return struct.pack('<II', 4, len(pickle)) + pickle


if __name__ == '__main__':
    unittest.main()


class PatchSetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.source = self.tmp / 'source'
        self.source.mkdir()
        run = lambda *args: subprocess.run(['git', *args], cwd=self.source, check=True, capture_output=True, text=True).stdout.strip()
        run('init', '-q')
        self.commits = []
        for name in ('old', 'v12', 'mid', 'v13', 'new'):
            run('-c', 'user.name=t', '-c', 'user.email=t@example.com', 'commit', '-q', '--allow-empty', '-m', name)
            self.commits.append(run('rev-parse', 'HEAD'))
        old, v12, mid, v13, new = self.commits
        for version, base in (('0.1.9', old), ('0.1.12', v12), ('0.1.13', v13)):
            folder = self.tmp / 'repo/patches' / version
            folder.mkdir(parents=True)
            (folder / 'base.txt').write_text(base + '\n')
        (self.tmp / 'repo/patches/0.1.13/checks.json').write_text('{}')
        (self.tmp / 'repo/checks.json').write_text('{"shared": true}')
        self.patches = [patch.object(customize, 'REPO', self.tmp / 'repo'), patch.object(customize, 'SOURCE', self.source),
                        patch.object(customize, 'PATCH_SET', None)]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in self.patches:
            item.stop()

    def test_sets_sort_by_release_and_default_to_newest(self):
        self.assertEqual([f.name for f in customize.patch_sets()], ['0.1.9', '0.1.12', '0.1.13'])
        self.assertEqual(customize.patch_dir().name, '0.1.13')

    def test_installed_commit_picks_its_own_set_or_closest_older(self):
        old, v12, mid, v13, new = self.commits
        self.assertEqual(customize.choose_patch_set(v12).name, '0.1.12')
        self.assertEqual(customize.choose_patch_set(v13).name, '0.1.13')
        self.assertEqual(customize.choose_patch_set(mid).name, '0.1.12')
        self.assertEqual(customize.choose_patch_set(new).name, '0.1.13')

    def test_older_than_every_set(self):
        with patch.object(customize, 'patch_sets', return_value=customize.patch_sets()[1:]):
            self.assertIsNone(customize.choose_patch_set(self.commits[0]))
            self.assertTrue(customize.older_than_patches(self.commits[0]))

    def test_checks_file_prefers_the_set_then_the_shared_file(self):
        customize.PATCH_SET = self.tmp / 'repo/patches/0.1.13'
        self.assertEqual(customize.checks_file().name, 'checks.json')
        self.assertEqual(customize.checks_file().parent.name, '0.1.13')
        customize.PATCH_SET = self.tmp / 'repo/patches/0.1.12'
        self.assertEqual(customize.checks_file(), self.tmp / 'repo/checks.json')

    def test_legacy_flat_layout_is_one_set(self):
        flat = self.tmp / 'flat/patches'
        flat.mkdir(parents=True)
        (flat / 'base.txt').write_text(self.commits[1] + '\n')
        with patch.object(customize, 'REPO', self.tmp / 'flat'):
            self.assertEqual(customize.patch_sets(), [flat])


class ArchivedPatchSetTests(unittest.TestCase):
    def test_older_set_is_read_from_its_tag(self):
        tmp = Path(tempfile.mkdtemp())
        repo = tmp / 'repo'
        run = lambda *args: subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@example.com', *args],
                                           cwd=repo, check=True, capture_output=True, text=True).stdout.strip()
        for version, base in (('0.1.12', 'a' * 40), ('0.1.13', 'b' * 40)):
            folder = repo / 'patches' / version
            folder.mkdir(parents=True)
            (folder / 'base.txt').write_text(base + '\n')
            (folder / '0001-x.patch').write_text(version)
        run('init', '-q')
        run('add', '-A')
        run('commit', '-q', '-m', 'both sets')
        run('tag', 'patches-0.1.12')
        run('rm', '-rq', 'patches/0.1.12')
        run('commit', '-q', '-m', 'only the newest set')
        with patch.object(customize, 'REPO', repo), patch.object(customize, 'CACHE', tmp / 'cache'):
            sets = customize.patch_sets()
            self.assertEqual([f.name for f in sets], ['0.1.12', '0.1.13'])
            self.assertEqual(sets[0], tmp / 'cache/patch-sets/0.1.12')
            self.assertEqual((sets[0] / '0001-x.patch').read_text(), '0.1.12')
            self.assertEqual(sets[1], repo / 'patches/0.1.13')
            # A second call reuses the extracted copy.
            self.assertEqual(customize.patch_sets()[0], sets[0])
