$ErrorActionPreference = "Stop"

function Resolve-Python {
    $bundled = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    if (Test-Path $bundled) {
        return $bundled
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return $python.Source
    }

    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        return $py.Source
    }

    throw "Python was not found. Install Python 3 or run this from Codex with the bundled runtime available."
}

$pythonExe = Resolve-Python
$scriptPath = Join-Path $PSScriptRoot "tools\build_index.py"
& $pythonExe $scriptPath @args
