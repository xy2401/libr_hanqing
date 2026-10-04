param(
    [Parameter(Mandatory)][string]$Source,
    [Parameter(Mandatory)][string]$Output,
    [Parameter(Mandatory)][int]$X,
    [Parameter(Mandatory)][int]$Y,
    [Parameter(Mandatory)][int]$Width,
    [Parameter(Mandatory)][int]$Height,
    [ValidateRange(1, 4)][int]$Scale = 1
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$sourcePath = (Resolve-Path -LiteralPath $Source).Path
$outputPath = [System.IO.Path]::GetFullPath($Output)
if (Test-Path -LiteralPath $outputPath) { throw 'Do not overwrite an existing crop.' }
$bitmap = [System.Drawing.Bitmap]::FromFile($sourcePath)
$crop = $null
$graphics = $null
try {
    if ($X -lt 0 -or $Y -lt 0 -or $Width -le 0 -or $Height -le 0 -or
        $X + $Width -gt $bitmap.Width -or $Y + $Height -gt $bitmap.Height) {
        throw 'Crop rectangle is outside the source image.'
    }
    [System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($outputPath)) | Out-Null
    $crop = [System.Drawing.Bitmap]::new($Width * $Scale, $Height * $Scale)
    $graphics = [System.Drawing.Graphics]::FromImage($crop)
    $graphics.DrawImage($bitmap, [System.Drawing.Rectangle]::new(0, 0, $crop.Width, $crop.Height),
        [System.Drawing.Rectangle]::new($X, $Y, $Width, $Height), [System.Drawing.GraphicsUnit]::Pixel)
    $crop.Save($outputPath, [System.Drawing.Imaging.ImageFormat]::Png)
    $record = [ordered]@{
        source = $sourcePath; source_sha256 = (Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash.ToLowerInvariant()
        source_dimensions = @($bitmap.Width, $bitmap.Height); rectangle_xywh = @($X, $Y, $Width, $Height)
        scale = $Scale; output = $outputPath; output_sha256 = (Get-FileHash -LiteralPath $outputPath -Algorithm SHA256).Hash.ToLowerInvariant()
        purpose = 'Visual inspection only; no text recognition'
    }
    $record | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath "$outputPath.json" -Encoding utf8
    $record | ConvertTo-Json -Compress
} finally {
    if ($graphics) { $graphics.Dispose() }
    if ($crop) { $crop.Dispose() }
    $bitmap.Dispose()
}
