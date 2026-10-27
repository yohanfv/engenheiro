# Voz do rádio do engenheiro (usa a voz do próprio Windows).
# O engenheiro.py manda cada frase em uma linha (texto em Base64/UTF-8) e espera o "OK".
param([int]$Velocidade = 1, [int]$Volume = 100, [string]$Idioma = 'pt')

Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$v = $s.GetInstalledVoices() | Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.Name -like ($Idioma + '*') } | Select-Object -First 1
if ($v) { $s.SelectVoice($v.VoiceInfo.Name); [Console]::Out.WriteLine('VOZ:' + $v.VoiceInfo.Name) }
else { [Console]::Out.WriteLine('VOZ:SEM_PORTUGUES') }
$s.Rate = [Math]::Max(-10, [Math]::Min(10, $Velocidade))
$s.Volume = [Math]::Max(0, [Math]::Min(100, $Volume))
[Console]::Out.Flush()

while ($true) {
    $l = [Console]::In.ReadLine()
    if ($l -eq $null) { break }
    if ($l.Length -gt 0) {
        try {
            $t = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($l))
            $s.Speak($t)
        } catch {}
    }
    [Console]::Out.WriteLine('OK')
    [Console]::Out.Flush()
}
