# Instala a recolha diária do SNIRH neste PC.
# Corre com duplo clique em instalar_snirh.bat. Pode ser repetido sem estragar nada.

$ErrorActionPreference = 'Stop'
$Repo     = 'https://github.com/researchaee/obs-onr-26.git'
$Destino  = Join-Path $env:USERPROFILE 'ONR\obs-onr-26'
$Tarefa   = 'ONR - Recolha SNIRH'
$Hora     = '13:17'

function Passo($t) { Write-Host "`n== $t" -ForegroundColor Cyan }
function Atualizar-Path {
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
                [Environment]::GetEnvironmentVariable('Path', 'User')
}
function Tem($cmd) { $null -ne (Get-Command $cmd -ErrorAction SilentlyContinue) }

# 1. Git
Passo 'Git'
if (-not (Tem 'git')) {
    if (Tem 'winget') {
        Write-Host 'A instalar o Git...'
        winget install --id Git.Git -e --silent --accept-package-agreements --accept-source-agreements
        Atualizar-Path
    }
    if (-not (Tem 'git')) {
        Write-Host 'Não encontrei o Git. Instala-o em https://git-scm.com/download/win e volta a correr este instalador.' -ForegroundColor Red
        exit 1
    }
}
git --version

# 2. Python
Passo 'Python'
function Python-Ok {
    try { & py -3 --version *> $null; if ($LASTEXITCODE -eq 0) { return 'py' } } catch {}
    try { & python --version *> $null; if ($LASTEXITCODE -eq 0) { return 'python' } } catch {}
    return $null
}
$Py = Python-Ok
if (-not $Py) {
    if (Tem 'winget') {
        Write-Host 'A instalar o Python 3.12...'
        winget install --id Python.Python.3.12 -e --silent --scope user --accept-package-agreements --accept-source-agreements
        Atualizar-Path
        $Py = Python-Ok
    }
    if (-not $Py) {
        Write-Host 'Não encontrei o Python. Instala-o em https://www.python.org/downloads/ (marca "Add python.exe to PATH") e volta a correr este instalador.' -ForegroundColor Red
        exit 1
    }
}
if ($Py -eq 'py') { & py -3 --version } else { & python --version }

# 3. Repositório
Passo "Repositório em $Destino"
if (Test-Path (Join-Path $Destino '.git')) {
    git -C $Destino pull --rebase
} else {
    New-Item -ItemType Directory -Force -Path (Split-Path $Destino) | Out-Null
    git clone $Repo $Destino
}
if (-not (git -C $Destino config user.name))  { git -C $Destino config user.name  'researchaee' }
if (-not (git -C $Destino config user.email)) { git -C $Destino config user.email 'researchaee@users.noreply.github.com' }

# 4. Bibliotecas
Passo 'Bibliotecas Python'
if ($Py -eq 'py') { & py -3 -m pip install --user --quiet --upgrade requests openpyxl }
else              { & python -m pip install --user --quiet --upgrade requests openpyxl }

# 5. Tarefa agendada
Passo "Tarefa agendada '$Tarefa', todos os dias às $Hora"
$Bat = Join-Path $Destino 'scripts\windows\recolha_snirh.bat'
$Acao = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument "/c `"$Bat`"" -WorkingDirectory $Destino
$Quando = New-ScheduledTaskTrigger -Daily -At $Hora
$Def = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Hours 1) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $Tarefa -Action $Acao -Trigger $Quando -Settings $Def `
    -Description 'Observatório Nacional do Regadio: volume e cota das albufeiras (SNIRH) para o GitHub' -Force | Out-Null
Write-Host 'Tarefa criada. Se o PC estiver desligado à hora marcada, corre quando voltar a ligar.'

# 6. Primeira recolha, já (traz a série desde 1990; pode demorar até 30 minutos)
Passo 'Primeira recolha (o Git pode abrir o browser para entrares no GitHub)'
& cmd.exe /c "`"$Bat`""
$Log = Join-Path $env:LOCALAPPDATA 'ONR\recolha_snirh.log'
Write-Host "`nÚltimas linhas do registo ($Log):"
Get-Content $Log -Tail 25

Passo 'Feito'
Write-Host 'Confirma no GitHub um commit "Clima SNIRH: recolha do PC" e o ficheiro dados/clima/_Recolhas_SNIRH.csv.'
