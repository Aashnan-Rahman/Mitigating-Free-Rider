param([string]$Commit='v15.4-completed-study')
$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '../../../..')).Path
$git=(Get-Command git -ErrorAction Stop).Source
$revision=(& $git -C $root rev-parse $Commit).Trim()
if($LASTEXITCODE -ne 0){throw 'Cannot resolve baseline source commit'}
$destination=Join-Path $PSScriptRoot 'evidence/completed_baselines'
$objects=@{}
foreach($line in (& $git -C $root ls-tree -r $revision -- results)) {
 if($line -match '^\d+ blob ([0-9a-f]{40})\t(results/fedavg_(?:cifar10|mnist)_baseline_seed(?:43|73)_fr30_fr40/[^/]+/(?:summary|protocol)\.json|results/fedavg_(?:cifar10|mnist)_baseline_seed(?:43|73)_fr30_fr40/[^/]+/(?:round_timings|client_metrics)\.csv)$') {$objects[$Matches[2]]=$Matches[1]}
}
$paths=@($objects.Keys|Sort-Object)
$files=[Collections.Generic.List[object]]::new()
# Bound command length and archive memory. No models or checkpoints are read.
for($offset=0;$offset -lt $paths.Count;$offset+=40) {
 $chunk=@($paths|Select-Object -Skip $offset -First 40)
 $info=[Diagnostics.ProcessStartInfo]::new($git)
 $info.WorkingDirectory=$root;$info.UseShellExecute=$false
 $info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true;$info.CreateNoWindow=$true
 foreach($arg in @('-c','core.autocrlf=false','-c','core.eol=lf','archive','--format=zip',$revision)+$chunk){$info.ArgumentList.Add($arg)}
 $process=[Diagnostics.Process]::Start($info);$buffer=[IO.MemoryStream]::new()
 $process.StandardOutput.BaseStream.CopyTo($buffer);$errors=$process.StandardError.ReadToEnd();$process.WaitForExit()
 if($process.ExitCode -ne 0){throw "Baseline archive failed: $errors"}
 $buffer.Position=0;$zip=[IO.Compression.ZipArchive]::new($buffer,[IO.Compression.ZipArchiveMode]::Read)
 try {
  foreach($entry in $zip.Entries) {
   if(-not $objects.ContainsKey($entry.FullName)){continue}
   $copy=[IO.MemoryStream]::new();$stream=$entry.Open()
   try{$stream.CopyTo($copy);$bytes=$copy.ToArray()}finally{$stream.Dispose();$copy.Dispose()}
   $header=[Text.Encoding]::UTF8.GetBytes("blob $($bytes.Length)`0")
   $all=[byte[]]::new($header.Length+$bytes.Length)
   [Array]::Copy($header,0,$all,0,$header.Length);[Array]::Copy($bytes,0,$all,$header.Length,$bytes.Length)
   $blob=[Convert]::ToHexString([Security.Cryptography.SHA1]::HashData($all)).ToLowerInvariant()
   if($blob -ne $objects[$entry.FullName]){throw "Baseline Git object mismatch: $($entry.FullName)"}
   $sha=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant()
   $target=Join-Path $destination $entry.FullName
   if(Test-Path -LiteralPath $target) {
    if((Get-FileHash $target -Algorithm SHA256).Hash.ToLowerInvariant() -ne $sha){throw "Existing baseline snapshot differs: $target"}
   } else {New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent)|Out-Null;[IO.File]::WriteAllBytes($target,$bytes)}
   $files.Add([pscustomobject]@{source=$entry.FullName;snapshot=$entry.FullName;git_blob_sha1=$blob;sha256=$sha;bytes=$bytes.Length})
  }
 } finally {$zip.Dispose();$buffer.Dispose();$process.Dispose()}
}
if($files.Count -ne $paths.Count){throw 'Missing baseline snapshot files'}
New-Item -ItemType Directory -Force -Path $destination|Out-Null
@{commit=$revision;files=$files;selection='Published records only; live completed records are discovered separately; no checkpoint/model import'}|ConvertTo-Json -Depth 7|Set-Content (Join-Path $destination 'import_provenance.json') -Encoding utf8
"Imported $($files.Count) byte-verified baseline record files from $revision"
