"""Windows T3 Code built and assembled from WSL.

Windows hosts without Git, Python or Node can still build a customized T3 Code:
the tool runs inside WSL, builds every bundle on Linux (the same way upstream's
release workflow builds the Windows JavaScript), rebuilds the Linux WSL runtime
the Windows app ships, and lays everything over a copy of the Windows app on the
Windows filesystem. Windows-only steps (the PE integrity resource, the Start menu
shortcut, process checks) go through Windows PowerShell, which every Windows has.
"""
import base64
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import subprocess
import tarfile


class WslError(Exception):
    pass


WSL_RUNTIME_ARCHIVE = 'wsl-runtime.tar.gz'
WSL_RUNTIME_HASH = WSL_RUNTIME_ARCHIVE + '.sha256'
STOCK_POWERSHELL = '/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe'


def is_wsl(release=None, interop='/proc/sys/fs/binfmt_misc/WSLInterop'):
    release = (release if release is not None else platform.release()).lower()
    return 'microsoft' in release or 'wsl' in release or os.path.exists(interop)


def powershell():
    found = shutil.which('powershell.exe')
    if found:
        return found
    if os.path.exists(STOCK_POWERSHELL):
        return STOCK_POWERSHELL
    raise WslError('Windows PowerShell is not reachable from WSL (is Windows interop enabled?).')


def encode_command(script):
    return base64.b64encode(script.encode('utf-16le')).decode('ascii')


def run_powershell(script, check=True):
    """Run a script in Windows PowerShell and return its stdout. Never builds a shell string."""
    # A Linux working directory becomes a UNC path PowerShell warns about; Windows' own drive is quiet.
    cwd = '/mnt/c' if os.path.isdir('/mnt/c') else None
    result = subprocess.run([powershell(), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                             '-EncodedCommand', encode_command("$ProgressPreference='SilentlyContinue';" + script)],
                            cwd=cwd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if check and result.returncode:
        raise WslError('Windows PowerShell failed: ' + (result.stderr.strip() or result.stdout.strip())[-2000:])
    return result.stdout


def ps_string(value):
    """A PowerShell single-quoted literal."""
    return "'" + str(value).replace("'", "''") + "'"


def ps_json_argument(value):
    """Pass structured data into PowerShell without quoting it into the script text."""
    data = base64.b64encode(json.dumps(value).encode('utf-8')).decode('ascii')
    return f"([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{data}')) | ConvertFrom-Json)"


def to_windows_path(path):
    result = subprocess.run(['wslpath', '-w', str(path)], capture_output=True, text=True)
    if result.returncode:
        raise WslError(f'Cannot map {path} to a Windows path: {result.stderr.strip()}')
    return result.stdout.strip()


def to_wsl_path(path):
    result = subprocess.run(['wslpath', '-u', str(path)], capture_output=True, text=True)
    if result.returncode:
        raise WslError(f'Cannot map {path} to a WSL path: {result.stderr.strip()}')
    return Path(result.stdout.strip())


def windows_folders():
    """LOCALAPPDATA and APPDATA of the Windows user, as WSL paths."""
    out = run_powershell("[Environment]::GetFolderPath('LocalApplicationData'); [Environment]::GetFolderPath('ApplicationData')")
    lines = [line.strip() for line in out.splitlines() if line.strip()]
    if len(lines) != 2:
        raise WslError('Could not read the Windows user folders.')
    return {'LOCALAPPDATA': str(to_wsl_path(lines[0])), 'APPDATA': str(to_wsl_path(lines[1]))}


# --- Electron ASAR integrity resource -----------------------------------------------

INTEGRITY_CSHARP = r'''
using System;
using System.Runtime.InteropServices;
using System.Collections.Generic;
using System.Text;
public static class T3CustomizeIntegrity {
  [DllImport("kernel32.dll", SetLastError=true, CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string f, IntPtr h, uint flags);
  [DllImport("kernel32.dll", SetLastError=true, CharSet=CharSet.Unicode)] static extern IntPtr FindResourceW(IntPtr m, string name, string type);
  [DllImport("kernel32.dll", SetLastError=true)] static extern uint SizeofResource(IntPtr m, IntPtr r);
  [DllImport("kernel32.dll", SetLastError=true)] static extern IntPtr LoadResource(IntPtr m, IntPtr r);
  [DllImport("kernel32.dll", SetLastError=true)] static extern IntPtr LockResource(IntPtr r);
  [DllImport("kernel32.dll", SetLastError=true)] static extern bool FreeLibrary(IntPtr m);
  [DllImport("kernel32.dll", SetLastError=true, CharSet=CharSet.Unicode)] static extern IntPtr BeginUpdateResourceW(string f, bool deleteExisting);
  [DllImport("kernel32.dll", SetLastError=true, CharSet=CharSet.Unicode)] static extern bool UpdateResourceW(IntPtr h, string type, string name, ushort lang, byte[] data, uint size);
  [DllImport("kernel32.dll", SetLastError=true)] static extern bool EndUpdateResourceW(IntPtr h, bool discard);
  public delegate bool EnumLanguages(IntPtr m, IntPtr type, IntPtr name, ushort lang, IntPtr param);
  [DllImport("kernel32.dll", SetLastError=true, CharSet=CharSet.Unicode)] static extern bool EnumResourceLanguagesW(IntPtr m, string type, string name, EnumLanguages callback, IntPtr param);
  static bool Missing(int error) { return error == 1812 || error == 1813 || error == 1814; }
  static Exception Fail(string what) { return new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error(), what); }
  public static string Read(string file) {
    IntPtr module = LoadLibraryExW(file, IntPtr.Zero, 2);
    if (module == IntPtr.Zero) throw Fail("LoadLibraryEx");
    try {
      IntPtr resource = FindResourceW(module, "ElectronAsar", "Integrity");
      if (resource == IntPtr.Zero) { if (Missing(Marshal.GetLastWin32Error())) return null; throw Fail("FindResource"); }
      IntPtr loaded = LoadResource(module, resource);
      if (loaded == IntPtr.Zero) throw Fail("LoadResource");
      IntPtr data = LockResource(loaded);
      uint size = SizeofResource(module, resource);
      byte[] bytes = new byte[size];
      Marshal.Copy(data, bytes, 0, (int)size);
      return Encoding.UTF8.GetString(bytes);
    } finally { FreeLibrary(module); }
  }
  public static void Write(string file, string json) {
    List<ushort> languages = new List<ushort>();
    IntPtr module = LoadLibraryExW(file, IntPtr.Zero, 2);
    if (module == IntPtr.Zero) throw Fail("LoadLibraryEx");
    EnumLanguages callback = (m, t, n, lang, p) => { languages.Add(lang); return true; };
    try {
      if (!EnumResourceLanguagesW(module, "Integrity", "ElectronAsar", callback, IntPtr.Zero) && !Missing(Marshal.GetLastWin32Error())) throw Fail("EnumResourceLanguages");
    } finally { FreeLibrary(module); GC.KeepAlive(callback); }
    if (languages.Count == 0) languages.Add(1033);
    byte[] payload = Encoding.UTF8.GetBytes(json);
    IntPtr update = BeginUpdateResourceW(file, false);
    if (update == IntPtr.Zero) throw Fail("BeginUpdateResource");
    foreach (ushort language in languages) {
      if (!UpdateResourceW(update, "Integrity", "ElectronAsar", language, payload, (uint)payload.Length)) {
        Exception error = Fail("UpdateResource");
        EndUpdateResourceW(update, true);
        throw error;
      }
    }
    if (!EndUpdateResourceW(update, false)) throw Fail("EndUpdateResource");
  }
}
'''


def windows_integrity(executable, values=None):
    """Read or replace Electron's embedded ASAR header hashes in a copied EXE, from WSL."""
    windows = to_windows_path(executable)
    script = 'Add-Type -TypeDefinition ' + ps_string(INTEGRITY_CSHARP) + ';'
    if values is None:
        script += ('$v = [T3CustomizeIntegrity]::Read(' + ps_string(windows) + ');'
                   'if ($v -eq $null) { "null" } else { [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($v)) }')
        out = run_powershell(script).strip().splitlines()[-1].strip()
        return None if out == 'null' else json.loads(base64.b64decode(out).decode('utf-8'))
    payload = base64.b64encode(json.dumps(values, separators=(',', ':')).encode('utf-8')).decode('ascii')
    script += ('[T3CustomizeIntegrity]::Write(' + ps_string(windows) + ', [Text.Encoding]::UTF8.GetString('
               "[Convert]::FromBase64String('" + payload + "')))")
    run_powershell(script)
    if windows_integrity(executable) != values:
        raise WslError('Windows ASAR integrity resource verification failed.')


# --- Launcher -----------------------------------------------------------------------

def windows_fingerprint(paths):
    """Size and last write time of Windows files, read by Windows itself."""
    items = [to_windows_path(p) for p in paths]
    script = ('$r = @(); foreach ($p in ' + ps_json_argument(items) + ') {'
              ' $i = Get-Item -LiteralPath $p; $r += [pscustomobject]@{ path = $i.FullName; size = $i.Length;'
              ' ticks = $i.LastWriteTimeUtc.Ticks } }; ConvertTo-Json -InputObject $r -Compress')
    return json.loads(run_powershell(script).strip() or '[]')


LAUNCH_PS1 = r'''# Written by t3code-customize. Opens the customized T3 Code while it matches the
# installed T3 Code, otherwise the installed (stock) one. Never changes either app.
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
function Notify($text) {
  try { (New-Object -ComObject WScript.Shell).Popup($text, 12, 'T3 Code (Customized)', 64) | Out-Null } catch {}
}
$state = Get-Content -Raw -LiteralPath (Join-Path $here 'launch.json') | ConvertFrom-Json
$target = $state.stockExe
$notice = $null
$matches = $true
foreach ($f in $state.stockFiles) {
  $i = Get-Item -LiteralPath $f.path -ErrorAction SilentlyContinue
  if (-not $i -or $i.Length -ne $f.size -or $i.LastWriteTimeUtc.Ticks -ne $f.ticks) { $matches = $false }
}
if (Test-Path -LiteralPath (Join-Path $here 'disabled')) {
} elseif (-not $state.buildExe -or -not (Test-Path -LiteralPath $state.buildExe)) {
  $notice = 'No customized build was found. Opening stock T3 Code.'
} elseif (-not $matches) {
  $notice = 'T3 Code was updated. Run t3code-customize in WSL to rebuild. Opening stock T3 Code.'
} else {
  $target = $state.buildExe
}
foreach ($name in 'ELECTRON_RUN_AS_NODE', 'ELECTRON_NO_ASAR', 'NODE_OPTIONS') {
  Remove-Item -LiteralPath ("Env:" + $name) -ErrorAction SilentlyContinue
}
$running = @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
  try { $_.Path -and (($_.Path -ieq $state.stockExe) -or ($_.Path -ieq $state.buildExe)) } catch { $false }
})
if ($running.Count -gt 0) {
  $other = @($running | Where-Object { $_.Path -ine $target })
  if ($other.Count -gt 0) {
    Notify ('T3 Code is already running from ' + $other[0].Path + '. Close all its windows and wait until it no longer appears in Task Manager, then open T3 Code (Customized) again.')
    exit 1
  }
}
if ($notice) { Notify $notice }
if ($target -ne $state.stockExe) { $env:T3CODE_DISABLE_AUTO_UPDATE = 'true' }
if ($args.Count -gt 0) { Start-Process -FilePath $target -ArgumentList $args } else { Start-Process -FilePath $target }
'''


def write_launcher(data, stock_exe, build_exe, stock_files):
    """launch.ps1 and launch.json in the Windows data folder."""
    data.mkdir(parents=True, exist_ok=True)
    (data / 'launch.ps1').write_text(LAUNCH_PS1.replace('\n', '\r\n'), encoding='utf-8-sig')
    state = {'stockExe': to_windows_path(stock_exe),
             'buildExe': to_windows_path(build_exe) if build_exe else None,
             'stockFiles': windows_fingerprint(stock_files)}
    (data / 'launch.json').write_text(json.dumps(state, indent=2), encoding='utf-8')
    return state


def write_shortcut(shortcut, data, icon):
    payload = {'path': to_windows_path(shortcut),
               'target': to_windows_path(powershell()) if powershell().startswith('/') else 'powershell.exe',
               'args': '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' +
                       to_windows_path(data / 'launch.ps1') + '"',
               'icon': to_windows_path(icon) + ',0' if icon else '',
               'cwd': to_windows_path(data)}
    shortcut.parent.mkdir(parents=True, exist_ok=True)
    run_powershell('$p = ' + ps_json_argument(payload) + '; $s = (New-Object -ComObject WScript.Shell).CreateShortcut($p.path);'
                   ' $s.TargetPath = $p.target; $s.Arguments = $p.args; $s.WorkingDirectory = $p.cwd;'
                   ' $s.WindowStyle = 7; if ($p.icon) { $s.IconLocation = $p.icon };'
                   " $s.Description = 'T3 Code with Stats for nerds'; $s.Save()")


def windows_processes_from(folder):
    """Paths of running Windows processes whose executable lives under folder."""
    script = ('$root = ' + ps_string(to_windows_path(folder).rstrip('\\') + '\\') + ';'
              ' @(Get-Process -ErrorAction SilentlyContinue | ForEach-Object { try { $_.Path } catch {} } |'
              ' Where-Object { $_ -and $_.StartsWith($root, [StringComparison]::OrdinalIgnoreCase) }) -join "`n"')
    return [line.strip() for line in run_powershell(script, check=False).splitlines() if line.strip()]


# --- WSL runtime archive --------------------------------------------------------------

def file_digest(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def runtime_stem(names):
    tops = {PurePosixPath(name).parts[0] for name in names if name and name != '.'}
    if len(tops) != 1:
        raise WslError('The WSL runtime archive must contain a single top-level directory, found: ' + ', '.join(sorted(tops)))
    return tops.pop()


def _replaced(name, stem):
    relative = name[len(stem) + 1:] if name.startswith(stem + '/') else None
    return relative is not None and (relative == 't3' or relative == 'client' or relative.startswith('client/'))


def _client_members(stem, client, template):
    """TarInfo and source path for the rebuilt web client, in a stable order."""
    entries = []
    def info(name, kind, mode, size=0):
        item = tarfile.TarInfo(name)
        item.type, item.mode, item.size = kind, mode, size
        item.uid, item.gid, item.uname, item.gname, item.mtime = (template.uid, template.gid, template.uname,
                                                                  template.gname, template.mtime)
        return item
    entries.append((info(f'{stem}/client', tarfile.DIRTYPE, 0o755), None))
    for path in sorted(Path(client).rglob('*'), key=lambda p: p.relative_to(client).as_posix()):
        if path.is_symlink():
            raise WslError('Unexpected symlink in the rebuilt web client: ' + str(path))
        name = f'{stem}/client/' + path.relative_to(client).as_posix()
        if path.is_dir():
            entries.append((info(name, tarfile.DIRTYPE, 0o755), None))
        elif path.is_file() and path.suffix != '.map':
            # Like upstream's archive build: source maps stay out of the runtime.
            entries.append((info(name, tarfile.REGTYPE, 0o644, path.stat().st_size), path))
    return entries


def rebuild_runtime_archive(stock, output, executable, client):
    """Write stock's WSL runtime archive with its t3 executable and web client replaced.

    Every other entry (native node_modules, resource monitor, libatomic and its
    license) is copied byte for byte from the installed app's own archive, so no
    Linux native code is rebuilt and nothing from a Windows build leaks in.
    """
    with tarfile.open(stock, 'r|gz') as source:
        names = []
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('wb') as raw, gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0, compresslevel=6) as zipped, \
                tarfile.open(fileobj=zipped, mode='w|', format=tarfile.GNU_FORMAT) as target:
            stem = None
            client_written = False
            for member in source:
                names.append(member.name)
                stem = stem or PurePosixPath(member.name).parts[0]
                if PurePosixPath(member.name).parts[0] != stem:
                    raise WslError('The WSL runtime archive has more than one top-level directory.')
                if member.name == f'{stem}/t3':
                    if not member.isfile():
                        raise WslError('The stock WSL runtime t3 entry is not a regular file.')
                    replacement = tarfile.TarInfo(member.name)
                    for field in ('mode', 'uid', 'gid', 'uname', 'gname', 'mtime'):
                        setattr(replacement, field, getattr(member, field))
                    replacement.size = Path(executable).stat().st_size
                    with Path(executable).open('rb') as data:
                        target.addfile(replacement, data)
                    continue
                if _replaced(member.name, stem):
                    if not client_written:
                        template = member
                        for item, path in _client_members(stem, client, template):
                            if path is None:
                                target.addfile(item)
                            else:
                                with path.open('rb') as data:
                                    target.addfile(item, data)
                        client_written = True
                    continue
                target.addfile(member, source.extractfile(member) if member.isfile() else None)
            if stem is None or f'{stem}/t3' not in names or not client_written:
                raise WslError('The stock WSL runtime archive is missing t3 or its web client.')
    verify_runtime_archive(stock, output, executable, client)
    digest = file_digest(output)
    return stem, digest


def verify_runtime_archive(stock, output, executable, client):
    """Unchanged entries match stock byte for byte; replaced ones match the build."""
    def entries(path):
        found = {}
        with tarfile.open(path, 'r|gz') as archive:
            for member in archive:
                digest = None
                if member.isfile():
                    digest = hashlib.sha256()
                    data = archive.extractfile(member)
                    for chunk in iter(lambda: data.read(1 << 20), b''):
                        digest.update(chunk)
                    digest = digest.hexdigest()
                found[member.name] = (member.type, member.mode, member.linkname, digest)
        return found
    before, after = entries(stock), entries(output)
    stem = runtime_stem(before)
    for name, entry in before.items():
        if _replaced(name, stem):
            continue
        if after.get(name) != entry:
            raise WslError('WSL runtime archive verification failed for stock entry ' + name)
    t3 = after.get(f'{stem}/t3')
    if t3 is None or t3[3] != file_digest(executable) or not t3[1] & 0o100:
        raise WslError('WSL runtime archive verification failed for t3.')
    for path in Path(client).rglob('*'):
        if path.is_file() and path.suffix != '.map':
            name = f'{stem}/client/' + path.relative_to(client).as_posix()
            if after.get(name, (None,) * 4)[3] != file_digest(path):
                raise WslError('WSL runtime archive verification failed for ' + name)
    extra = [name for name in after if name not in before and not _replaced(name, stem)]
    if extra:
        raise WslError('Unexpected WSL runtime archive entries: ' + ', '.join(extra[:5]))


def write_runtime_hash(path, digest):
    # Same shape as upstream's sidecar: the hex digest and a newline.
    Path(path).write_text(digest + '\n', encoding='ascii', newline='\n')


# --- Copies on the Windows drive ------------------------------------------------------
# Copies through /mnt/c can be very slow; Windows copies the same bytes at disk
# speed, also from \\wsl.localhost.

def windows_copy_tree(source, destination):
    script = ('robocopy ' + ps_string(to_windows_path(source)) + ' ' + ps_string(to_windows_path(destination)) +
              ' /E /COPY:DAT /DCOPY:DAT /SL /NFL /NDL /NJH /NJS /NP /R:2 /W:1 | Out-Null; exit $LASTEXITCODE')
    result = subprocess.run([powershell(), '-NoProfile', '-NonInteractive', '-EncodedCommand', encode_command(script)],
                            cwd='/mnt/c', capture_output=True, text=True, errors='replace')
    # robocopy: 0-7 are success (bit flags for copied/extra/mismatched); 8 and up are failures.
    if result.returncode >= 8:
        raise WslError(f'Windows could not copy {source} to {destination} (robocopy {result.returncode}).')


def windows_copy_file(source, destination):
    Path(destination).parent.mkdir(parents=True, exist_ok=True)
    run_powershell('Copy-Item -LiteralPath ' + ps_string(to_windows_path(source)) + ' -Destination ' +
                   ps_string(to_windows_path(destination)) + ' -Force')
    if Path(destination).stat().st_size != Path(source).stat().st_size:
        raise WslError(f'Copying {source} to {destination} was incomplete.')


def windows_remove_tree(path):
    if Path(path).exists():
        run_powershell('Remove-Item -LiteralPath ' + ps_string(to_windows_path(path)) + ' -Recurse -Force', check=False)
    if Path(path).exists():
        shutil.rmtree(path, ignore_errors=True)


def windows_sha256(path):
    """SHA-256 of a file on the Windows drive, computed by Windows (reading it through /mnt/c is slow)."""
    out = run_powershell('(Get-FileHash -Algorithm SHA256 -LiteralPath ' + ps_string(to_windows_path(path)) + ').Hash')
    digest = out.strip().splitlines()[-1].strip().lower() if out.strip() else ''
    if len(digest) != 64:
        raise WslError('Windows could not hash ' + str(path))
    return digest
