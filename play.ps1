<#
.SYNOPSIS
  Run local Battlesnake games against the snake in main.py.

.DESCRIPTION
  Starts the Flask server, waits for it to answer, runs N games through the
  Battlesnake CLI, then shuts the server down and prints a summary. With
  -Snakes greater than 1 every snake points at the same server, which is a
  cheap way to test combat behaviour against itself.

.EXAMPLE
  .\play.ps1                        # 10 solo games
  .\play.ps1 -Games 25 -Snakes 4    # 25 four-way self-play games
  .\play.ps1 -Games 1 -Browser      # one game, watched in the browser
#>
param(
    [int]$Games = 10,
    [int]$Snakes = 1,
    [int]$Width = 11,
    [int]$Height = 11,
    [string]$GameType = "",
    [int]$Port = 8000,
    [switch]$Browser
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not $GameType) {
    if ($Snakes -le 1) { $GameType = "solo" } else { $GameType = "standard" }
}

$python = ".\.venv\Scripts\python.exe"
$cli = ".\tools\battlesnake.exe"
foreach ($required in @($python, $cli, ".\main.py")) {
    if (-not (Test-Path $required)) { throw "missing $required" }
}

$url = "http://127.0.0.1:$Port"
$env:PORT = "$Port"
$server = Start-Process -FilePath $python -ArgumentList "main.py" -WindowStyle Hidden -PassThru

try {
    $ready = $false
    for ($i = 0; $i -lt 40; $i++) {
        try {
            Invoke-RestMethod $url -TimeoutSec 2 | Out-Null
            $ready = $true
            break
        } catch {
            Start-Sleep -Milliseconds 250
        }
    }
    if (-not $ready) { throw "server did not start on $url" }
    Write-Host "Server up on $url - $GameType, $Snakes snake(s), $Games game(s)`n"

    $gameArgs = @("play", "-W", "$Width", "-H", "$Height", "-g", $GameType)
    for ($s = 1; $s -le $Snakes; $s++) {
        $name = if ($Snakes -eq 1) { "Daugherty" } else { "Daugherty-$s" }
        $gameArgs += @("--name", $name, "--url", $url)
    }
    if ($Browser) { $gameArgs += "--browser" }

    $results = @()
    for ($g = 1; $g -le $Games; $g++) {
        # The CLI logs to stderr. Redirecting it inside PowerShell would wrap
        # every line in an ErrorRecord, so capture both streams to files.
        $outFile = [System.IO.Path]::GetTempFileName()
        $errFile = [System.IO.Path]::GetTempFileName()
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        Start-Process -FilePath $cli -ArgumentList ($gameArgs + @("-r", "$g")) `
            -NoNewWindow -Wait -RedirectStandardOutput $outFile -RedirectStandardError $errFile | Out-Null
        $sw.Stop()
        $output = "" + (Get-Content $outFile -Raw) + (Get-Content $errFile -Raw)
        Remove-Item $outFile, $errFile -Force -ErrorAction SilentlyContinue

        $turns = 0
        if ($output -match "Game completed after (\d+) turns") { $turns = [int]$Matches[1] }
        $winner = ""
        if ($output -match "(\S+) was the winner") { $winner = $Matches[1] }
        elseif ($output -match "It was a draw") { $winner = "draw" }
        elseif ($GameType -eq "solo") { $winner = "solo" }

        $results += [pscustomobject]@{
            Game    = $g
            Turns   = $turns
            Winner  = $winner
            Seconds = [math]::Round($sw.Elapsed.TotalSeconds, 1)
            MsPerTurn = if ($turns -gt 0) { [math]::Round($sw.Elapsed.TotalMilliseconds / $turns, 1) } else { 0 }
        }
        Write-Host ("game {0,3}: {1,4} turns  {2,6}s  {3,5} ms/turn  {4}" -f $g, $turns, $results[-1].Seconds, $results[-1].MsPerTurn, $winner)
    }

    $stats = $results | Measure-Object -Property Turns -Average -Minimum -Maximum
    Write-Host "`n--- summary over $Games game(s) ---"
    Write-Host ("turns  avg {0}  min {1}  max {2}" -f [math]::Round($stats.Average, 1), $stats.Minimum, $stats.Maximum)
    Write-Host ("worst ms/turn  {0}" -f ($results | Measure-Object -Property MsPerTurn -Maximum).Maximum)

    # Games that end almost immediately mean a hard safety bug, not bad luck.
    $early = @($results | Where-Object { $_.Turns -le 3 })
    if ($early.Count -gt 0) {
        Write-Host ("WARNING: {0} game(s) ended by turn 3 - check the safety filter" -f $early.Count) -ForegroundColor Red
    }
    $results | Group-Object Winner | Sort-Object Count -Descending |
        ForEach-Object { Write-Host ("wins  {0,-16} {1}" -f $_.Name, $_.Count) }
} finally {
    Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
}
