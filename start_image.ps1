# PowerShell script to start the container image on Windows
# Usage: .\start_image.ps1 [-Refresh] [-Engine <docker|podman>] [-Help]

#  options: omnivaultx, omnivaultx-core, omnivaultx-min
$image_name="omnivaultx"

param(
    [switch]$Refresh,
    [ValidateSet('docker','podman')]
    [string]$Engine = 'docker',
    [switch]$Help
)

function Show-Help {
    Write-Host "Usage: .\\start_image.ps1 [-Refresh] [-Engine <docker|podman>] [-Help]"
    Write-Host " -Refresh           Refresh the container image"
    Write-Host " -Engine <engine>   Set container engine (docker or podman, default: docker)"
    Write-Host " -Help              Display this help message"
}

if ($Help) {
    Show-Help
    exit 0
}

# Check if .env file exists
if (!(Test-Path .env)) {
    Write-Host "Error: .env file not found" -ForegroundColor Red
    exit 1
}

# Function to generate a random 32 character encryption key (base64, no / or newline)
function Generate-EncryptionKey {
    $bytes = [System.Security.Cryptography.RandomNumberGenerator]::GetBytes(24)
    $key = [Convert]::ToBase64String($bytes).Replace("/","")
    if ($key.Length -lt 32) {
        $key = $key + "A" * (32 - $key.Length)
    }
    return $key.Substring(0,32)
}

# Check if ENCRYPTION_KEY exists and is 32 characters
$envLines = Get-Content .env
$keyLine = $envLines | Where-Object { $_ -match '^ENCRYPTION_KEY=' }
$key = $null
if ($keyLine) {
    $key = $keyLine -replace '^ENCRYPTION_KEY=', ''
}
if (-not $key -or $key.Length -ne 32) {
    Write-Host "Generating new ENCRYPTION_KEY, since it was not found or is not 32 characters..."
    $envLines = $envLines | Where-Object { $_ -notmatch '^ENCRYPTION_KEY=' }
    $newKey = Generate-EncryptionKey
    $envLines += "ENCRYPTION_KEY=$newKey"
    $envLines | Set-Content .env -NoNewline
    Write-Host "New ENCRYPTION_KEY has been generated and added to .env file"
}

# Check if container engine is available
if (-not (Get-Command $Engine -ErrorAction SilentlyContinue)) {
    Write-Host "$Engine is not installed or not in PATH. Please install $Engine and ensure it is accessible from the command line." -ForegroundColor Yellow
    exit 1
}

# Check if Python3 is available
if (-not (Get-Command python3 -ErrorAction SilentlyContinue)) {
    Write-Host "Python3 is not installed or not in PATH. Please install Python3 and ensure it is accessible from the command line if you need meta extractors." -ForegroundColor Yellow
}

# Create host directories if they don't exist
$dirs = @(".\data\db", ".\data\fs", ".\data\rabbitmq", ".\data\temp")
foreach ($dir in $dirs) {
    if (!(Test-Path $dir)) {
        Write-Host "Creating missing $dir directory"
        New-Item -ItemType Directory -Path $dir | Out-Null
    }
}

Write-Host "Stopping container if it exists"
& $Engine stop $image_name 2>$null

if ($Refresh) {
    Write-Host "Removing existing container if it exists"
    & $Engine rm -f $image_name 2>$null
}

Write-Host "Pulling container image"
& $Engine pull madrent/$image_name:latest

Write-Host "Running container"
& $Engine run -d --name $image_name `
    --env-file ./.env `
    -p 80:80 `
    -p 15672:15672 `
    -p 5672:5672 `
    -p 8000:8000 `
    -v "$(Resolve-Path .\data\db):/app/backend/database" `
    -v "$(Resolve-Path .\data\fs):/app/backend/fs" `
    -v "$(Resolve-Path .\data\rabbitmq):/var/lib/rabbitmq" `
    -v "$(Resolve-Path .\data\temp):/app/backend/temp" `
    $image_name

Write-Host "Printing logs"
& $Engine logs -f $image_name 