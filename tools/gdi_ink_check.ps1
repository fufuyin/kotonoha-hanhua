# Independent ink test: render each probed code point with GDI+ (System.Drawing)
# using the OTF directly, and count non-black pixels.
# Output: ASCII only, "U+XXXX ink=N".
Add-Type -AssemblyName System.Drawing

$fontPath = 'F:\Application\Unity\fonts\NotoSansCJKsc-Regular.otf'
$cpsPath  = 'F:\Application\Unity\probe_cps.txt'
$outPath  = 'F:\Application\Unity\gdi_ink.txt'

$pfc = New-Object System.Drawing.Text.PrivateFontCollection
$pfc.AddFontFile($fontPath)
$family = $pfc.Families[0]
$font = New-Object System.Drawing.Font($family, 64, [System.Drawing.FontStyle]::Regular, [System.Drawing.GraphicsUnit]::Pixel)

$bmp = New-Object System.Drawing.Bitmap(160, 160)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.Clear([System.Drawing.Color]::Black)
$g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit

function Get-Ink([int]$cp) {
  $g.Clear([System.Drawing.Color]::Black)
  $s = [string][char]$cp
  $g.DrawString($s, $font, [System.Drawing.Brushes]::White, 0, 0)
  $n = 0
  for ($y = 0; $y -lt 160; $y += 2) {
    for ($x = 0; $x -lt 160; $x += 2) {
      $c = $bmp.GetPixel($x, $y)
      if ($c.R -gt 40) { $n++ }
    }
  }
  return $n
}

$lines = New-Object System.Collections.Generic.List[string]
$lines.Add("# family=$($family.Name) font=$fontPath")
foreach ($k in @(0x0041, 0x4E00, 0xFF1F, 0x3000, 0x30FB, 0x301C, 0x2026, 0x2014)) {
  $ink = Get-Ink $k
  $lines.Add(("CONTROL U+{0:X4} ink={1}" -f $k, $ink))
}
$zero = 0
$nonzero = 0
foreach ($line in [System.IO.File]::ReadAllLines($cpsPath)) {
  $t = $line.Trim()
  if ($t.Length -eq 0) { continue }
  $cp = [Convert]::ToInt32($t.Substring(2), 16)
  $ink = Get-Ink $cp
  if ($ink -eq 0) { $zero++ } else { $nonzero++ }
  $lines.Add(("U+{0:X4} ink={1}" -f $cp, $ink))
}
$lines.Add("# zero-ink=$zero nonzero-ink=$nonzero")
[System.IO.File]::WriteAllLines($outPath, $lines, [System.Text.Encoding]::ASCII)
Write-Host "wrote $outPath  zero=$zero nonzero=$nonzero"
$g.Dispose(); $bmp.Dispose(); $font.Dispose(); $pfc.Dispose()
