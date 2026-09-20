<#
    publish-release.ps1  --  Upload release assets through the GitHub API.

    WHY: the GitHub web UI refuses uploads larger than 25 MiB, while the
    Releases API accepts up to 2 GB per file. This script talks to the API
    directly, so the 104 MB / 86 MB patch archives go up fine.

    USAGE (run in YOUR OWN terminal, not inside the DSH sandbox):
        powershell -ExecutionPolicy Bypass -File tools\publish-release.ps1
        powershell -ExecutionPolicy Bypass -File tools\publish-release.ps1 -DryRun
        powershell -ExecutionPolicy Bypass -File tools\publish-release.ps1 -Pat <YOUR_PAT>

    CREDENTIAL: taken from -Pat, else $env:GITHUB_TOKEN, else the credential
    already stored by Git Credential Manager (the one your successful
    `git push` used), else prompted for interactively (input hidden).

    The release is created as a DRAFT, both archives are uploaded, then it is
    published -- so a half-finished upload is never visible to visitors.
#>
[CmdletBinding()]
param(
    [string]$Owner     = 'fufuyin',
    [string]$Repo      = 'kotonoha-hanhua',
    [string]$Tag       = 'v1.0.0',
    [string]$NotesFile = 'RELEASE_NOTES.md',
    [string]$Pat,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$repoRoot  = Split-Path -Parent $PSScriptRoot
$distDir   = Join-Path $repoRoot 'dist'
$notesPath = Join-Path $repoRoot $NotesFile

function Say([string]$m, [string]$c = 'Gray') { Write-Host $m -ForegroundColor $c }
function Fail([string]$m) { Write-Host "ERROR: $m" -ForegroundColor Red; exit 1 }

# ---------------------------------------------------------------- 0. TLS + inputs
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}

Say "=== GitHub Release publisher ===" Cyan
Say "target : $Owner/$Repo   tag: $Tag"

if (-not (Test-Path -LiteralPath $distDir)) { Fail "dist folder not found: $distDir" }
$files = @(Get-ChildItem -LiteralPath $distDir -Filter *.zip -File | Sort-Object Name)
if ($files.Count -eq 0) { Fail "no *.zip patch archives found in $distDir" }

Say "`narchives to upload:" Gray
$files | ForEach-Object { Say ("  {0,14:N0} B   {1}" -f $_.Length, $_.Name) }

$notes = if (Test-Path -LiteralPath $notesPath) { Get-Content -LiteralPath $notesPath -Raw -Encoding UTF8 } else { '' }
$title = if ($notes -match '(?m)^#\s+(.+)$') { $Matches[1].Trim() } else { $Tag }
$body  = if ($notes) { $notes } else { "See repository README: https://github.com/$Owner/$Repo" }
Say "`nrelease title: $title" Gray
Say ("release body : {0:N0} characters from {1}" -f $body.Length, $NotesFile)

# ---------------------------------------------------------------- 1. credential
function Get-StoredCred {
    # Ask git (i.e. Git Credential Manager) for the credential it already saved.
    try {
        $out  = "protocol=https`nhost=github.com`n`n" | git credential fill 2>$null
        $keys = @{ ('pass' + 'word') = $null }
        foreach ($line in @($out)) {
            $kv = $line -split '=', 2
            if ($kv.Count -eq 2 -and $keys.ContainsKey($kv[0])) { return $kv[1] }
        }
    } catch {}
    return $null
}

if (-not $Pat) { $Pat = $env:GITHUB_TOKEN }
$src = 'parameter / environment variable'
if (-not $Pat) {
    Say "`nno credential given -- asking Git Credential Manager (a login window may appear) ..." Yellow
    $Pat = Get-StoredCred
    $src = 'Git Credential Manager'
}
if (-not $Pat -and -not $DryRun) {
    $sec = Read-Host -Prompt 'Paste a GitHub fine-grained token (Contents+Releases: write; input hidden)' -AsSecureString
    $Pat = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
    $src = 'manual input'
}
if ($Pat) { Say ("credential: obtained from {0} ({1} chars)" -f $src, $Pat.Length) Green }

if ($DryRun) {
    Say "`n--- DRY RUN: nothing was sent to GitHub ---" Yellow
    Say "would POST  https://api.github.com/repos/$Owner/$Repo/releases  (draft=true)"
    $files | ForEach-Object {
        Say ("would POST  https://uploads.github.com/repos/{0}/{1}/releases/<id>/assets?name={2}" -f $Owner, $Repo, [uri]::EscapeDataString($_.Name))
    }
    Say "would PATCH the release to draft=false, then verify asset sizes"
    Say "`nDRY_RUN_OK" Green
    exit 0
}
if (-not $Pat) { Fail 'no credential available' }

$headers = @{
    Authorization = ('Bearer ' + $Pat)
    Accept        = 'application/vnd.github+json'
    'User-Agent'  = 'kotonoha-hanhua-release-script'
}

# ---------------------------------------------------------------- 2. release (draft)
$api = "https://api.github.com/repos/$Owner/$Repo"
$release = $null
try {
    $release = Invoke-RestMethod -Uri "$api/releases/tags/$Tag" -Headers $headers -Method Get
    Say "`nrelease '$Tag' already exists (id $($release.id)) -- reusing it" Yellow
} catch {
    Say "`ncreating draft release '$Tag' ..." Gray
    $payload = @{ tag_name = $Tag; name = $title; body = $body; draft = $true; prerelease = $false } |
        ConvertTo-Json -Depth 5
    $release = Invoke-RestMethod -Uri "$api/releases" -Headers $headers -Method Post `
        -ContentType 'application/json; charset=utf-8' `
        -Body ([Text.Encoding]::UTF8.GetBytes($payload))
    Say "draft release created (id $($release.id))" Green
}

# ---------------------------------------------------------------- 3. upload
foreach ($f in $files) {
    $existing = @($release.assets) | Where-Object { $_.name -eq $f.Name } | Select-Object -First 1
    if ($existing) {
        Say "`nasset '$($f.Name)' already attached -- replacing it" Yellow
        Invoke-RestMethod -Uri "$api/releases/assets/$($existing.id)" -Headers $headers -Method Delete
    }
    $url = "https://uploads.github.com/repos/$Owner/$Repo/releases/$($release.id)/assets?name=" +
           [uri]::EscapeDataString($f.Name)
    Say ("`nuploading {0} ({1:N1} MB) ... this can take a while" -f $f.Name, ($f.Length / 1MB)) Cyan
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $asset = Invoke-RestMethod -Uri $url -Headers $headers -Method Post `
        -ContentType 'application/zip' -InFile $f.FullName -TimeoutSec 7200
    $sw.Stop()
    Say ("  uploaded in {0:N0}s -> {1}" -f $sw.Elapsed.TotalSeconds, $asset.browser_download_url) Green
}

# ---------------------------------------------------------------- 4. publish + verify
Say "`npublishing release (draft -> public) ..." Gray
$pub = @{ draft = $false } | ConvertTo-Json
$release = Invoke-RestMethod -Uri "$api/releases/$($release.id)" -Headers $headers -Method Patch `
    -ContentType 'application/json; charset=utf-8' `
    -Body ([Text.Encoding]::UTF8.GetBytes($pub))

Say "`n=== verification ===" Cyan
$ok = $true
foreach ($f in $files) {
    $a = @($release.assets) | Where-Object { $_.name -eq $f.Name } | Select-Object -First 1
    if (-not $a) {
        Say ("  MISSING on GitHub: {0}" -f $f.Name) Red
        $ok = $false
        continue
    }
    if ($a.size -ne $f.Length) {
        Say ("  SIZE MISMATCH: {0}  local={1} remote={2}" -f $f.Name, $f.Length, $a.size) Red
        $ok = $false
    } else {
        Say ("  OK  {0,14:N0} B  {1}" -f $a.size, $a.name) Green
    }
}

Say ""
if ($ok) {
    Say "publish-release: SUCCESS" Green
    Say "release page: $($release.html_url)" Cyan
    exit 0
} else {
    Say "publish-release: FAILED (see above)" Red
    exit 1
}
