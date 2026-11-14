param(
    [string]$Blender,
    [string]$BlendFile,
    [switch]$Check,
    [switch]$Isolated,
    [switch]$NoTunnel
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$source = Join-Path $root 'easykig'
$profile = Join-Path $root '.blender-dev'
$savedBlender = Join-Path $profile 'blender-path.txt'

if (!$Blender -and (Test-Path -LiteralPath $savedBlender -PathType Leaf)) {
    $Blender = (Get-Content -LiteralPath $savedBlender -Raw).Trim()
}
if (!$Blender) {
    $Blender = Join-Path $env:ProgramFiles 'Blender Foundation/Blender 5.1/blender.exe'
    if (!(Test-Path -LiteralPath $Blender -PathType Leaf)) {
        $command = Get-Command blender.exe -CommandType Application -ErrorAction SilentlyContinue
        if ($command) {
            $Blender = $command.Source
        }
    }
}
if (!(Test-Path -LiteralPath $Blender -PathType Leaf)) {
    throw 'Blender executable not found. Pass -Blender with the full path to blender.exe.'
}
$Blender = (Resolve-Path -LiteralPath $Blender).Path

$repository = Join-Path $profile 'repository'
$link = Join-Path $repository 'easykig'
New-Item -ItemType Directory -Path $repository -Force | Out-Null
$existing = Get-Item -LiteralPath $link -Force -ErrorAction SilentlyContinue
if ($existing) {
    if ($existing.LinkType -ne 'Junction' -or $existing.Target -ne $source) {
        throw "The development extension path already exists and points somewhere else: $link"
    }
} else {
    New-Item -ItemType Junction -Path $link -Target $source | Out-Null
}
Set-Content -LiteralPath $savedBlender -Value $Blender -Encoding UTF8

$previousResources = $env:BLENDER_USER_RESOURCES
$previousRepository = $env:EASYKIG_DEV_REPOSITORY
$previousTunnel = $env:EASYKIG_DEV_AUTO_TUNNEL
try {
    if ($Isolated) {
        $env:BLENDER_USER_RESOURCES = $profile
    }
    $env:EASYKIG_DEV_REPOSITORY = $repository
    $env:EASYKIG_DEV_AUTO_TUNNEL = if ($Check -or $NoTunnel) { '0' } else { '1' }

    $blenderArguments = @()
    if ($Check) {
        $blenderArguments += '--background'
    }
    if ($BlendFile) {
        $blenderArguments += (Resolve-Path -LiteralPath $BlendFile).Path
    }
    $bootstrap = @'
import os
import sys
from pathlib import Path
import addon_utils
import bpy

module_name = 'bl_ext.easykig_dev.easykig'
repository = Path(os.environ['EASYKIG_DEV_REPOSITORY']).resolve()
repos = bpy.context.preferences.extensions.repos
repo = next((item for item in repos if item.module == 'easykig_dev'), None)
if repo is None:
    repo = next((item for item in repos if Path(item.directory).resolve() == repository), None)
    if repo is None:
        result = bpy.ops.preferences.extension_repo_add(
            name='EasyKig Development', type='LOCAL',
            use_custom_directory=True, custom_directory=str(repository),
        )
        if result != {'FINISHED'}:
            raise RuntimeError('Could not add the EasyKig development repository')
        repo = next(item for item in repos if Path(item.directory).resolve() == repository)
    repo.module = 'easykig_dev'
if Path(repo.directory).resolve() != repository:
    raise RuntimeError('The EasyKig development repository already points elsewhere')
if repo.source != 'SYSTEM':
    repo.source = 'SYSTEM'

for entry in tuple(bpy.context.preferences.addons):
    if entry.module != module_name and entry.module.rsplit('.', 1)[-1] == 'easykig':
        addon_utils.disable(entry.module, default_set=False)
_, loaded = addon_utils.check(module_name)
addon = sys.modules[module_name] if loaded else addon_utils.enable(module_name, default_set=True)
if addon is None or not hasattr(bpy.types.Scene, 'easykig_settings'):
    raise RuntimeError('Could not enable the EasyKig development extension')
print('Blender preferences:', bpy.utils.user_resource('CONFIG'), flush=True)
print('EasyKig source:', Path(addon.__file__).resolve(), flush=True)
prefs = bpy.context.preferences.addons[module_name].preferences
if prefs.ssh_auto_connect and os.environ.get('EASYKIG_DEV_AUTO_TUNNEL') == '1':
    from bl_ext.easykig_dev.easykig import connections
    try:
        connections.start_from_preferences()
        print('EasyKig SSH: connecting using saved preferences', flush=True)
    except (OSError, ValueError, RuntimeError) as exc:
        print('EasyKig SSH:', exc, flush=True)
'@
    $blenderArguments += @('--python-exit-code', '1', '--python-expr', $bootstrap)
    & $Blender @blenderArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Blender exited with code $LASTEXITCODE."
    }
} finally {
    $env:BLENDER_USER_RESOURCES = $previousResources
    $env:EASYKIG_DEV_REPOSITORY = $previousRepository
    $env:EASYKIG_DEV_AUTO_TUNNEL = $previousTunnel
}
