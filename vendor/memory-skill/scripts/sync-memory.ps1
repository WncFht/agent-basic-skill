$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Runtime = Join-Path $ScriptDir "..\runtime\memory_runtime.py"

if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 $Runtime sync @args
    exit $LASTEXITCODE
}

if (Get-Command python -ErrorAction SilentlyContinue) {
    & python $Runtime sync @args
    exit $LASTEXITCODE
}

Write-Error "memory runtime error`nWhat happened: Could not find a Python 3 interpreter for memory-skill.`nWhy it matters: The memory runtime is implemented in Python so it can behave consistently on Windows, Linux, and macOS.`nHow to fix: Install Python 3 and ensure `py -3` or `python` is available on PATH, then retry this command."
exit 1
