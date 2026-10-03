# Compile cover typography and publication assets; does not generate or recognize art.
# Requires Windows GDI+, Node.js, and the sharp package.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$BookDirectory,
    [Parameter(Mandatory = $true)][string]$Title,
    [Parameter(Mandatory = $true)][string]$Author,
    [string]$NodeExecutable = 'node',
    [string]$SharpModule = 'sharp',
    [ValidateSet('ink', 'oil')][string]$Profile = 'ink',
    [string]$FontFamilyName = ''
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$bookPath = (Resolve-Path -LiteralPath $BookDirectory).Path
$imagePath = Join-Path $bookPath 'images'
$publicationPath = Join-Path $bookPath 'src\epub\images'
$sourcePath = Join-Path $imagePath 'cover.source.png'
if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
    throw 'Place the unchanged generated artwork at images/cover.source.png first.'
}
$outputPaths = @(
    (Join-Path $imagePath 'cover.jpg'),
    (Join-Path $imagePath 'cover.svg'),
    (Join-Path $imagePath 'cover.preview.jpg'),
    (Join-Path $publicationPath 'cover.svg')
)
foreach ($outputPath in $outputPaths) {
    if (Test-Path -LiteralPath $outputPath) {
        throw "Refusing to overwrite an existing cover asset: $outputPath"
    }
}
[void](New-Item -ItemType Directory -Path $publicationPath -Force)
if (-not $FontFamilyName) {
    $FontFamilyName = if ($Profile -eq 'ink') { 'KaiTi' } else { 'Microsoft YaHei' }
}
$fontStyle = if ($Profile -eq 'ink') { [System.Drawing.FontStyle]::Regular } else { [System.Drawing.FontStyle]::Bold }
$fontWeight = if ($Profile -eq 'ink') { '400' } else { '700' }
$textColor = if ($Profile -eq 'ink') { '#202924' } else { '#fff' }
$fontFamily = New-Object System.Drawing.FontFamily($FontFamilyName)
if (-not $fontFamily.IsStyleAvailable($fontStyle)) {
    throw 'The requested font style is unavailable.'
}
$culture = [System.Globalization.CultureInfo]::InvariantCulture
function Format-Coordinate([double]$Value) {
    return $Value.ToString('0.###', $culture)
}

function Convert-OutlineToSvg([System.Drawing.Drawing2D.GraphicsPath]$Outline) {
    $points = $Outline.PathPoints
    $types = $Outline.PathTypes
    $commands = New-Object System.Collections.Generic.List[string]
    $index = 0
    while ($index -lt $points.Length) {
        $type = $types[$index] -band 7
        $point = $points[$index]
        $coordinates = "$(Format-Coordinate $point.X) $(Format-Coordinate $point.Y)"
        if ($type -eq 0) {
            $commands.Add("M $coordinates")
        } elseif ($type -eq 1) {
            $commands.Add("L $coordinates")
        } elseif ($type -eq 3) {
            if ($index + 2 -ge $points.Length) { throw 'Incomplete cubic glyph contour.' }
            $second = $points[$index + 1]
            $third = $points[$index + 2]
            $commands.Add("C $coordinates $(Format-Coordinate $second.X) $(Format-Coordinate $second.Y) $(Format-Coordinate $third.X) $(Format-Coordinate $third.Y)")
            $index += 2
        } else { throw "Unsupported glyph contour: $type" }
        if (($types[$index] -band 128) -ne 0) { $commands.Add('Z') }
        $index++
    }
    return "<path fill=`"$textColor`" d=`"$($commands -join ' ')`"/>"
}

function New-CoverLine([string]$Text, [double]$Height, [double]$Top) {
    $probe = New-Object System.Drawing.Drawing2D.GraphicsPath
    $probe.AddString($Text, $fontFamily, [int]$fontStyle, 108, [System.Drawing.PointF]::Empty, [System.Drawing.StringFormat]::GenericTypographic)
    $scale = $Height / $probe.GetBounds().Height
    $probe.Dispose()
    $fontSize = 108 * $scale
    $advance = $fontSize + 5
    $outline = New-Object System.Drawing.Drawing2D.GraphicsPath
    for ($index = 0; $index -lt $Text.Length; $index++) {
        $point = New-Object System.Drawing.PointF([single]($index * $advance), 0)
        $outline.AddString($Text[$index].ToString(), $fontFamily, [int]$fontStyle, [single]$fontSize, $point, [System.Drawing.StringFormat]::GenericTypographic)
    }
    $bounds = $outline.GetBounds()
    if ($bounds.Width -gt 1320) { throw 'Cover text exceeds the 40px side padding.' }
    $offsetX = (1400 - $bounds.Width) / 2 - $bounds.X
    $offsetY = $Top - $bounds.Y
    $matrix = New-Object System.Drawing.Drawing2D.Matrix
    $matrix.Translate([single]$offsetX, [single]$offsetY)
    $outline.Transform($matrix)
    $matrix.Dispose()
    $compiledText = Convert-OutlineToSvg $outline
    $outline.Dispose()
    $baseline = $offsetY + $fontSize * $fontFamily.GetCellAscent($fontStyle) / $fontFamily.GetEmHeight($fontStyle)
    $positions = @()
    for ($index = 0; $index -lt $Text.Length; $index++) {
        $positions += Format-Coordinate ($offsetX + $index * $advance)
    }
    $escapedText = [System.Security.SecurityElement]::Escape($Text)
    return @{
        Editable = "<text x=`"$($positions -join ' ')`" y=`"$(Format-Coordinate $baseline)`" font-family=`"$FontFamilyName`" font-weight=`"$fontWeight`" font-size=`"$(Format-Coordinate $fontSize)`" fill=`"$textColor`">$escapedText</text>"
        Compiled = $compiledText
        FontSize = $fontSize
        GlyphHeight = $Height
        GlyphTop = $Top
    }
}

function New-CoverColumn([string]$Text, [double]$Height, [double]$Top, [double]$CenterX, [double]$Gap) {
    $probe = New-Object System.Drawing.Drawing2D.GraphicsPath
    $probe.AddString($Text, $fontFamily, [int]$fontStyle, 108, [System.Drawing.PointF]::Empty, [System.Drawing.StringFormat]::GenericTypographic)
    $fontSize = 108 * $Height / $probe.GetBounds().Height
    $probe.Dispose()
    $positionsX = @()
    $positionsY = @()
    $outlines = @()
    for ($index = 0; $index -lt $Text.Length; $index++) {
        $outline = New-Object System.Drawing.Drawing2D.GraphicsPath
        $outline.AddString($Text[$index].ToString(), $fontFamily, [int]$fontStyle, [single]$fontSize, [System.Drawing.PointF]::Empty, [System.Drawing.StringFormat]::GenericTypographic)
        $bounds = $outline.GetBounds()
        $offsetX = $CenterX - $bounds.Width / 2 - $bounds.X
        $offsetY = $Top + $index * ($Height + $Gap) + ($Height - $bounds.Height) / 2 - $bounds.Y
        if ($CenterX - $bounds.Width / 2 -lt 40 -or $CenterX + $bounds.Width / 2 -gt 1360 -or $Top + ($index + 1) * ($Height + $Gap) -gt 2060) {
            $outline.Dispose()
            throw 'Vertical cover text exceeds the 40px canvas padding.'
        }
        $matrix = New-Object System.Drawing.Drawing2D.Matrix
        $matrix.Translate([single]$offsetX, [single]$offsetY)
        $outline.Transform($matrix)
        $matrix.Dispose()
        $outlines += Convert-OutlineToSvg $outline
        $outline.Dispose()
        $positionsX += Format-Coordinate $offsetX
        $positionsY += Format-Coordinate ($offsetY + $fontSize * $fontFamily.GetCellAscent($fontStyle) / $fontFamily.GetEmHeight($fontStyle))
    }
    $escapedText = [System.Security.SecurityElement]::Escape($Text)
    return @{
        Editable = "<text x=`"$($positionsX -join ' ')`" y=`"$($positionsY -join ' ')`" font-family=`"$FontFamilyName`" font-weight=`"$fontWeight`" font-size=`"$(Format-Coordinate $fontSize)`" fill=`"$textColor`">$escapedText</text>"
        Compiled = $outlines -join "`n  "
        FontSize = $fontSize
        GlyphHeight = $Height
        GlyphTop = $Top
    }
}

try {
    if ($Profile -eq 'ink') {
        $titleLine = New-CoverColumn $Title 110 210 1110 32
        $authorLine = New-CoverColumn $Author 52 650 950 22
    } else {
        $titleLine = New-CoverLine $Title 80 1770
        $authorLine = New-CoverLine $Author 40 1910
    }
} finally { $fontFamily.Dispose() }
$renderScript = @'
const fs = require('node:fs');
const path = require('node:path');
const sharp = require(process.argv[1]);
const book = process.argv[2];
(async () => {
  const images = path.join(book, 'images');
  const source = path.join(images, 'cover.source.png');
  const dimensions = await sharp(source).metadata();
  if (dimensions.width * 3 !== dimensions.height * 2) throw new Error('Artwork must have a 2:3 portrait ratio; cropping requires a separate design decision.');
  await sharp(source).resize(1400, 2100).flatten({background: '#000'}).jpeg({quality: 90, mozjpeg: true}).toFile(path.join(images, 'cover.jpg'));
  if (fs.statSync(path.join(images, 'cover.jpg')).size > 1500000) throw new Error('Background exceeds the 1.5 MB cover limit.');
})().catch(error => {console.error(error.message); process.exitCode = 1;});
'@
& $NodeExecutable -e $renderScript $SharpModule $bookPath
if ($LASTEXITCODE -ne 0) { throw 'Background preparation failed.' }
$escapedTitle = [System.Security.SecurityElement]::Escape($Title)
$escapedAuthor = [System.Security.SecurityElement]::Escape($Author)
$artStyle = if ($Profile -eq 'ink') { '水墨' } else { '油畫' }
$description = "《$escapedTitle》，$escapedAuthor。原創$($artStyle)風格封面。"
$panel = if ($Profile -eq 'oil') { '  <rect x="0" y="1700" width="1400" height="320" fill="#000"/>' } else { '' }
$jpegData = [Convert]::ToBase64String([IO.File]::ReadAllBytes((Join-Path $imagePath 'cover.jpg')))
$editable = @"
<?xml version="1.0" encoding="utf-8"?>
<svg xmlns="http://www.w3.org/2000/svg" version="1.1" viewBox="0 0 1400 2100">
  <title>《$escapedTitle》封面</title>
  <desc>$description</desc>
  <image xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="cover.jpg" x="0" y="0" width="1400" height="2100"/>
$panel
  $($titleLine.Editable)
  $($authorLine.Editable)
</svg>
"@
$compiled = @"
<?xml version="1.0" encoding="utf-8"?>
<svg xmlns="http://www.w3.org/2000/svg" version="1.1" viewBox="0 0 1400 2100">
  <title>《$escapedTitle》封面</title>
  <desc>$description</desc>
  <image xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="data:image/jpeg;base64,$jpegData" x="0" y="0" width="1400" height="2100"/>
$panel
  $($titleLine.Compiled)
  $($authorLine.Compiled)
</svg>
"@
$utf8 = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllText((Join-Path $imagePath 'cover.svg'), $editable + "`n", $utf8)
[IO.File]::WriteAllText((Join-Path $publicationPath 'cover.svg'), $compiled + "`n", $utf8)
$previewScript = @'
const path = require('node:path');
const sharp = require(process.argv[1]);
const book = process.argv[2];
sharp(path.join(book, 'src', 'epub', 'images', 'cover.svg')).resize(1400, 2100).jpeg({quality: 90, mozjpeg: true}).toFile(path.join(book, 'images', 'cover.preview.jpg')).catch(error => {console.error(error.message); process.exitCode = 1;});
'@
& $NodeExecutable -e $previewScript $SharpModule $bookPath
if ($LASTEXITCODE -ne 0) { throw 'Cover preview rendering failed.' }
[PSCustomObject]@{
    Book = $bookPath
    Width = 1400
    Height = 2100
    TitleFontSize = $titleLine.FontSize
    AuthorFontSize = $authorLine.FontSize
    TitleGlyphHeight = $titleLine.GlyphHeight
    AuthorGlyphHeight = $authorLine.GlyphHeight
    Font = $FontFamilyName
    FontStyle = $fontStyle.ToString()
    Profile = $Profile
} | ConvertTo-Json
