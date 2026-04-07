# Yigthinker one-line installer for Windows
# Usage: irm https://raw.githubusercontent.com/gaoyu/Yigthinker/master/install.ps1 | iex
$ErrorActionPreference = "Stop"

function Main {
    $uvPath = Get-Command uv -ErrorAction SilentlyContinue
    if ($uvPath) {
        Write-Host "uv found: $(uv --version)"
    } else {
        Write-Host "Installing uv..."
        Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression

        # Refresh PATH for current session
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "User") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "Machine")

        $uvPath = Get-Command uv -ErrorAction SilentlyContinue
        if (-not $uvPath) {
            Write-Host "Error: uv installation failed. Install manually: https://docs.astral.sh/uv/" -ForegroundColor Red
            exit 1
        }
    }

    Write-Host ""
    Write-Host "Starting Yigthinker installer..."
    Write-Host ""
    uvx yigthinker install
}

Main
