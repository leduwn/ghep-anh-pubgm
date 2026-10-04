param(
    [Parameter(Mandatory = $true)]
    [string]$ScriptPath
)

$resolvedScript = [System.IO.Path]::GetFullPath($ScriptPath)
if (-not (Test-Path -LiteralPath $resolvedScript -PathType Leaf)) {
    throw "Không tìm thấy Photoshop script: $resolvedScript"
}

$photoshop = New-Object -ComObject Photoshop.Application
$photoshop.Visible = $true
$oldDialogs = $photoshop.DisplayDialogs

try {
    $photoshop.DisplayDialogs = 3
    $photoshop.DoJavaScriptFile($resolvedScript) | Out-Null
}
finally {
    $photoshop.DisplayDialogs = $oldDialogs
}
