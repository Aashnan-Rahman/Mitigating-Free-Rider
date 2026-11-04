param([string]$Commit='8519fe180f337486e18dfc752cfedfcef64eaf53')
$ErrorActionPreference='Stop'
$repository=(Resolve-Path (Join-Path $PSScriptRoot '../../../..')).Path
$gitCandidates=@('C:/Users/Asus/AppData/Local/GitHubDesktop/app-3.6.7/resources/app/git/cmd/git.exe','C:/Users/Asus/AppData/Local/GitHubDesktop/app-3.6.6/resources/app/git/cmd/git.exe')
$git=@($gitCandidates | Where-Object {Test-Path -LiteralPath $_})[0]
if (-not $git) { $git=(Get-Command git -ErrorAction Stop).Source }
$sourceRoot='results/mnist_segment_timing_20261103'
$destination=Join-Path $PSScriptRoot 'evidence/timing_mnist_20261103'
$names=@('README.md','experiment_manifest.json','experiment_status.json','segment_comparison.csv','ours_phase_segments.csv',
'ours/round_timings.csv','ours/global_metrics.csv','ours/cycle_decisions.csv','ours/removals.csv','ours/run_config.json','ours/protocol.json','ours/timing_protocol.json','ours/timing_summary.json','ours/status.json','ours/latest_results.json',
'std/round_timings.csv','std/segment_timings.csv','std/protocol.json','std/summary.json','std/timing_summary.json','std/status.json','std/latest_results.json','std_segment_protocol.json')
$sourceNames=@('segment_timing.py','run_v154_segment_timing.py','run_std_segment_timing.py','configs/mnist_segment_timing_20261103.json')
$wanted=@{}; foreach ($name in $names) {$wanted["$sourceRoot/$name"]=$name}; foreach ($name in $sourceNames) {$wanted[$name]="source/$name"}
$expected=@{}
foreach ($line in (& $git -C $repository ls-tree -r $Commit -- $sourceRoot @sourceNames)) {
    if ($line -match '^\d+ blob ([0-9a-f]{40})\t(.+)$') {$expected[$Matches[2]]=$Matches[1]}
}
if ($LASTEXITCODE -ne 0) {throw 'Cannot read the pinned study commit'}
$start=[Diagnostics.ProcessStartInfo]::new($git)
$start.WorkingDirectory=$repository;$start.UseShellExecute=$false;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true;$start.CreateNoWindow=$true
foreach ($argument in @('-c','core.autocrlf=false','-c','core.eol=lf','archive','--format=zip',$Commit,$sourceRoot)+$sourceNames) {$start.ArgumentList.Add($argument)}
$process=[Diagnostics.Process]::Start($start)
$archiveBytes=[IO.MemoryStream]::new()
$process.StandardOutput.BaseStream.CopyTo($archiveBytes);$errorText=$process.StandardError.ReadToEnd();$process.WaitForExit()
if ($process.ExitCode -ne 0) {throw "Cannot archive study evidence: $errorText"}
$archiveBytes.Position=0
$archive=[IO.Compression.ZipArchive]::new($archiveBytes,[IO.Compression.ZipArchiveMode]::Read)
$manifest=[Collections.Generic.List[object]]::new()
try {
    foreach ($entry in $archive.Entries) {
        if (-not $wanted.ContainsKey($entry.FullName)) {continue}
        $buffer=[IO.MemoryStream]::new();$stream=$entry.Open()
        try {$stream.CopyTo($buffer);$bytes=$buffer.ToArray()} finally {$stream.Dispose();$buffer.Dispose()}
        $header=[Text.Encoding]::UTF8.GetBytes("blob $($bytes.Length)`0")
        $gitBytes=[byte[]]::new($header.Length+$bytes.Length)
        [Array]::Copy($header,0,$gitBytes,0,$header.Length);[Array]::Copy($bytes,0,$gitBytes,$header.Length,$bytes.Length)
        $blob=[Convert]::ToHexString([Security.Cryptography.SHA1]::HashData($gitBytes)).ToLowerInvariant()
        if ($blob -ne $expected[$entry.FullName]) {throw "Git object mismatch: $($entry.FullName), expected $($expected[$entry.FullName]), received $blob ($($bytes.Length) bytes)"}
        $sha256=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant()
        $target=Join-Path $destination $wanted[$entry.FullName]
        if (Test-Path -LiteralPath $target) {
            if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant() -ne $sha256) {throw "Existing evidence differs: $target"}
        } else {
            New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
            [IO.File]::WriteAllBytes($target,$bytes)
        }
        $manifest.Add([pscustomobject]@{source=$entry.FullName;snapshot=$wanted[$entry.FullName];bytes=$bytes.Length;git_blob_sha1=$blob;sha256=$sha256})
    }
} finally {$archive.Dispose();$archiveBytes.Dispose();$process.Dispose()}
if ($manifest.Count -ne $wanted.Count) {throw 'Missing timing evidence files'}
@{repository='https://github.com/Aashnan-Rahman/Mitigating-Free-Rider';branch='v15.4-completed-study';commit=$Commit;files=$manifest} | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $destination 'import_provenance.json') -Encoding utf8
Write-Output "Imported and SHA-verified $($manifest.Count) timing evidence files from $Commit"
