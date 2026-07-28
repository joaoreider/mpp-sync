param(
    [string]$InnoSetupCompiler = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$BuildDir = $PSScriptRoot
$RuntimeDir = Join-Path $BuildDir "runtime"
$JreZip = Join-Path $RuntimeDir "temurin-jre.zip"
$JreDir = Join-Path $RuntimeDir "jre"
$OdbcMsi = Join-Path $RuntimeDir "msodbcsql.msi"
$VenvDir = Join-Path $BuildDir ".venv-build"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"

$TemurinJreUrl = "https://api.adoptium.net/v3/binary/latest/21/ga/windows/x64/jre/hotspot/normal/eclipse"
$OdbcDriverUrl = "https://go.microsoft.com/fwlink/?linkid=2266337"

function Invoke-Download {
    param(
        [string]$Url,
        [string]$OutFile
    )

    if (Test-Path $OutFile) {
        Write-Host "Using cached $(Split-Path $OutFile -Leaf)"
        return
    }

    Write-Host "Downloading $Url"
    Invoke-WebRequest -Uri $Url -OutFile $OutFile
}

function Expand-Jre {
    if (Test-Path (Join-Path $JreDir "bin\server\jvm.dll")) {
        Write-Host "Using cached JRE"
        return
    }

    $ExtractDir = Join-Path $RuntimeDir "jre-extract"
    Remove-Item $ExtractDir -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item $JreDir -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Path $ExtractDir | Out-Null
    Expand-Archive -Path $JreZip -DestinationPath $ExtractDir -Force

    $InnerDir = Get-ChildItem -Path $ExtractDir -Directory | Select-Object -First 1
    if ($null -eq $InnerDir) {
        throw "JRE zip extraction did not produce a directory."
    }

    Move-Item -Path $InnerDir.FullName -Destination $JreDir
    Remove-Item $ExtractDir -Recurse -Force
}

Set-Location $Root
New-Item -ItemType Directory -Path $RuntimeDir -Force | Out-Null

if (-not (Test-Path $PythonExe)) {
    python -m venv $VenvDir
}

& $PythonExe -m pip install --upgrade pip
& $PythonExe -m pip install -r (Join-Path $Root "requirements.txt") pyinstaller

Invoke-Download -Url $TemurinJreUrl -OutFile $JreZip
Expand-Jre
Invoke-Download -Url $OdbcDriverUrl -OutFile $OdbcMsi

$DistApp = Join-Path $Root "dist\MPPSync"
Remove-Item $DistApp -Recurse -Force -ErrorAction SilentlyContinue
& $PythonExe -m PyInstaller --noconfirm (Join-Path $BuildDir "MPPSync.spec") --distpath (Join-Path $Root "dist") --workpath (Join-Path $BuildDir "pyinstaller-work")

$DistJre = Join-Path $DistApp "jre"
Remove-Item $DistJre -Recurse -Force -ErrorAction SilentlyContinue
Copy-Item $JreDir $DistJre -Recurse

if (-not (Test-Path $InnoSetupCompiler)) {
    throw "Inno Setup compiler not found at '$InnoSetupCompiler'. Install Inno Setup 6 or pass -InnoSetupCompiler."
}

& $InnoSetupCompiler (Join-Path $BuildDir "installer.iss")

Write-Host "Installer created at dist\MPPSync-Setup.exe"
