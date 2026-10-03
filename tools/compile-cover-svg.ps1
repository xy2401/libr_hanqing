# Compile the supported editable cover SVG vocabulary to self-contained outlined SVG.
# Does not modify artwork, generate images, or recognize text.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$SourceSvg,
    [Parameter(Mandatory = $true)][string]$OutputSvg,
    [Parameter(Mandatory = $true)][string]$PreviewPath,
    [string]$NodeExecutable = 'node',
    [string]$SharpModule = 'sharp'
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$sourcePath = (Resolve-Path -LiteralPath $SourceSvg).Path
$sourceDirectory = Split-Path -Parent $sourcePath
$outputPath = [IO.Path]::GetFullPath($OutputSvg)
$previewOutput = [IO.Path]::GetFullPath($PreviewPath)
foreach ($target in @($outputPath, $previewOutput)) {
    if (Test-Path -LiteralPath $target) { throw "Refusing to overwrite: $target" }
}
$document = New-Object System.Xml.XmlDocument
$document.XmlResolver = $null
$document.Load($sourcePath)
$svgNamespace = 'http://www.w3.org/2000/svg'
$xlinkNamespace = 'http://www.w3.org/1999/xlink'
$svg = $document.DocumentElement
if ($svg.NamespaceURI -ne $svgNamespace -or $svg.GetAttribute('viewBox') -ne '0 0 1400 2100') {
    throw 'Expected a 1400x2100 SVG cover.'
}
$culture = [Globalization.CultureInfo]::InvariantCulture
function Read-Numbers([string]$Value) {
    if (-not $Value) { return @() }
    return @($Value.Trim() -split '[,\s]+' | ForEach-Object { [double]::Parse($_, $culture) })
}
function Format-Coordinate([double]$Value) { return $Value.ToString('0.###', $culture) }
function Get-Contour([System.Drawing.Drawing2D.GraphicsPath]$Outline) {
    $points = $Outline.PathPoints
    $types = $Outline.PathTypes
    $commands = New-Object System.Collections.Generic.List[string]
    for ($index = 0; $index -lt $points.Length; $index++) {
        $point = $points[$index]
        $coordinates = "$(Format-Coordinate $point.X) $(Format-Coordinate $point.Y)"
        switch ($types[$index] -band 7) {
            0 { $commands.Add("M $coordinates") }
            1 { $commands.Add("L $coordinates") }
            3 {
                if ($index + 2 -ge $points.Length) { throw 'Incomplete cubic glyph contour.' }
                $second = $points[$index + 1]
                $third = $points[$index + 2]
                $commands.Add("C $coordinates $(Format-Coordinate $second.X) $(Format-Coordinate $second.Y) $(Format-Coordinate $third.X) $(Format-Coordinate $third.Y)")
                $index += 2
            }
            default { throw 'Unsupported glyph contour.' }
        }
        if (($types[$index] -band 128) -ne 0) { $commands.Add('Z') }
    }
    return $commands -join ' '
}

foreach ($node in @($svg.ChildNodes)) {
    if ($node.NodeType -ne [Xml.XmlNodeType]::Element) { continue }
    if ($node.LocalName -eq 'image') {
        $href = $node.GetAttribute('href', $xlinkNamespace)
        if (-not $href) { $href = $node.GetAttribute('href') }
        if ($href -like 'data:image/jpeg;base64,*') { continue }
        if ($href -match '^\w+:|^[/\\]') { throw 'Only local relative background image paths are supported.' }
        $background = [IO.Path]::GetFullPath((Join-Path $sourceDirectory $href))
        $sourcePrefix = $sourceDirectory.TrimEnd('\','/') + [IO.Path]::DirectorySeparatorChar
        if (-not $background.StartsWith($sourcePrefix,[StringComparison]::OrdinalIgnoreCase)) {
            throw 'Background must remain inside the editable SVG directory.'
        }
        $bytes = [IO.File]::ReadAllBytes($background)
        if ($bytes.Length -gt 1500000 -or $bytes[0] -ne 255 -or $bytes[1] -ne 216) { throw 'Expected a JPEG background under 1.5 MB.' }
        $node.SetAttribute('href', $xlinkNamespace, 'data:image/jpeg;base64,' + [Convert]::ToBase64String($bytes)) | Out-Null
        $node.RemoveAttribute('href')
        continue
    }
    if ($node.LocalName -ne 'text') {
        if ($node.LocalName -notin @('title','desc','rect','path')) { throw "Unsupported SVG element: $($node.LocalName)" }
        if ($node.HasAttribute('transform')) { throw 'Transforms are supported only on text.' }
        continue
    }
    if ($node.ChildNodes.Count -ne 1 -or $node.FirstChild.NodeType -ne [Xml.XmlNodeType]::Text) { throw 'Expected plain SVG text without tspan.' }
    $text = $node.InnerText
    $positionsX = @(Read-Numbers $node.GetAttribute('x'))
    $positionsY = @(Read-Numbers $node.GetAttribute('y'))
    if ($positionsX.Count -notin @(1,$text.Length) -or $positionsY.Count -notin @(1,$text.Length)) {
        throw 'Provide one x/y coordinate or an explicit coordinate for every character.'
    }
    $fontSize = [single]::Parse($node.GetAttribute('font-size'), $culture)
    $fontStyle = if ($node.GetAttribute('font-weight') -eq '700') { [Drawing.FontStyle]::Bold } else { [Drawing.FontStyle]::Regular }
    $fontFamily = New-Object Drawing.FontFamily($node.GetAttribute('font-family'))
    $outline = New-Object Drawing.Drawing2D.GraphicsPath
    try {
        $ascent = $fontSize * $fontFamily.GetCellAscent($fontStyle) / $fontFamily.GetEmHeight($fontStyle)
        if ($positionsX.Count -eq 1 -and $positionsY.Count -eq 1) {
            $origin = New-Object Drawing.PointF([single]$positionsX[0], [single]($positionsY[0] - $ascent))
            $outline.AddString($text,$fontFamily,[int]$fontStyle,$fontSize,$origin,[Drawing.StringFormat]::GenericTypographic)
        } else {
            for ($index = 0; $index -lt $text.Length; $index++) {
                $x = if ($positionsX.Count -eq 1) { $positionsX[0] } else { $positionsX[$index] }
                $y = if ($positionsY.Count -eq 1) { $positionsY[0] } else { $positionsY[$index] }
                $origin = New-Object Drawing.PointF([single]$x,[single]($y - $ascent))
                $outline.AddString($text[$index].ToString(),$fontFamily,[int]$fontStyle,$fontSize,$origin,[Drawing.StringFormat]::GenericTypographic)
            }
        }
        $transform = $node.GetAttribute('transform')
        if ($transform) {
            if ($transform -notmatch '^matrix\(([^)]+)\)$') { throw 'Only an SVG affine matrix is supported.' }
            $values = @(Read-Numbers $Matches[1])
            if ($values.Count -ne 6) { throw 'Affine matrix requires six numbers.' }
            $matrix = New-Object Drawing.Drawing2D.Matrix([single]$values[0],[single]$values[1],[single]$values[2],[single]$values[3],[single]$values[4],[single]$values[5])
            $outline.Transform($matrix)
            $matrix.Dispose()
        }
        $bounds = $outline.GetBounds()
        if ($bounds.Left -lt 40 -or $bounds.Top -lt 40 -or $bounds.Right -gt 1360 -or $bounds.Bottom -gt 2060) { throw 'Text exceeds canvas padding.' }
        $path = $document.CreateElement('path',$svgNamespace)
        $path.SetAttribute('fill',$node.GetAttribute('fill'))
        $path.SetAttribute('d',(Get-Contour $outline))
        [void]$svg.ReplaceChild($path,$node)
    } finally {
        $outline.Dispose()
        $fontFamily.Dispose()
    }
}
foreach ($target in @($outputPath, $previewOutput)) {
    [void](New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force)
}
$settings = New-Object Xml.XmlWriterSettings
$settings.Encoding = New-Object Text.UTF8Encoding($false)
$settings.Indent = $true
$settings.NewLineChars = "`n"
$writer = [Xml.XmlWriter]::Create($outputPath,$settings)
try { $document.Save($writer) } finally { $writer.Dispose() }
$renderer = @'
const sharp = require(process.argv[1]);
sharp(process.argv[2]).resize(1400,2100).jpeg({quality:90,mozjpeg:true}).toFile(process.argv[3]).catch(error=>{console.error(error.message);process.exitCode=1;});
'@
& $NodeExecutable -e $renderer $SharpModule $outputPath $previewOutput
if ($LASTEXITCODE -ne 0) { throw 'Preview rendering failed.' }
Write-Output "Compiled: $outputPath"
