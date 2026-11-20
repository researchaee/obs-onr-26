# Observatório Nacional do Regadio (ONR), 2.ª fase

Dados base do Observatório Nacional do Regadio e recolha automática da camada climática.

## Estrutura do repositório

| Caminho | O que é |
|---|---|
| `ONR_Dados_Curados.xlsx` | Livro curado com todas as tabelas do modelo (DGADR, IFAP, INE, Eurostat e dimensões). É mantido à mão pela equipa |
| `scripts/onr_clima_recolha.py` | Recolhedor da camada climática (IPMA e SNIRH) |
| `.github/workflows/clima-diario.yml` | Workflow do GitHub Actions que recolhe o IPMA |
| `scripts/windows/` | Recolha do SNIRH num PC em Portugal (tarefa agendada do Windows e instalador) |
| `dados/clima/` | Dados de clima acumulados pelo recolhedor, em CSV |

## Fluxos automáticos

Há dois fluxos, um por fonte, porque o SNIRH recusa ligações dos servidores do GitHub (HTTP 403).

| Fluxo | Onde corre | Quando | Grava |
|---|---|---|---|
| IPMA | GitHub Actions, workflow **Recolha diária de clima (IPMA)** | Todos os dias às 05:37 UTC, à mão em **Actions → Run workflow**, e quando o script ou o workflow mudam | `fClima_Diario.csv`, `fClima_Mensal.csv`, `_Recolhas.csv` |
| SNIRH | PC em Portugal, tarefa **ONR - Recolha SNIRH** do Agendador de Tarefas | Todos os dias às 13:17. Se o PC estiver desligado, corre quando voltar a ligar | `fClima_Albufeira.csv`, `_Recolhas_SNIRH.csv` |

Os dois fluxos nunca escrevem no mesmo ficheiro, por isso os commits não entram em conflito. Os dois fazem commit só quando há dados novos, o IPMA como `github-actions[bot]` («Clima IPMA: recolha de …») e o SNIRH a partir do PC («Clima SNIRH: recolha do PC»).

### Fontes recolhidas

| Fonte | Dados | Grão | Histórico |
|---|---|---|---|
| IPMA, dados abertos | Precipitação, temperatura máxima, média e mínima, ET0 | dia × concelho | Só uma janela de 20 dias. A série acumula-se a partir da primeira recolha e os dias não recolhidos perdem-se |
| APA/SNIRH | Volume armazenado e cota | dia × albufeira | Desde 1990. A primeira recolha traz a série completa e, se não acabar em 30 minutos, continua nos dias seguintes |

As albufeiras recolhidas são as da tabela `dAlbufeira` do `ONR_Dados_Curados.xlsx` que têm `SiteID_SNIRH` preenchido. Para acrescentar uma albufeira basta preencher esse campo no livro e fazer commit. A recolha seguinte traz a série completa dessa albufeira.

A água no solo do AgroClima não é recolhida, porque o IPMA não autorizou o uso desse serviço por terceiros.

### Instalar a recolha do SNIRH num PC

Requisitos: Windows, ligação à internet a partir de Portugal e acesso de escrita a este repositório.

1. Descarregar a pasta `scripts/windows/` e fazer duplo clique em `instalar_snirh.bat`.
2. O instalador instala o Git e o Python se faltarem, clona o repositório para `%USERPROFILE%\ONR\obs-onr-26`, cria a tarefa agendada e faz a primeira recolha.
3. Na primeira recolha o Git abre o browser para entrar no GitHub. Isto só acontece uma vez.

O registo local de cada execução fica em `%LOCALAPPDATA%\ONR\recolha_snirh.log`. O instalador pode ser corrido de novo sem estragar nada.

## Dados produzidos

Todos os ficheiros estão em `dados/clima/`, em CSV UTF-8, separados por vírgula e com ponto decimal.

| Ficheiro | Conteúdo | Colunas |
|---|---|---|
| `fClima_Diario.csv` | Clima ao dia, últimos 400 dias | Ano, Data, IDConcelho, Indicador, Unidade, Valor, Dispersao, Fonte |
| `fClima_Mensal.csv` | Clima ao mês, meses completos mais antigos | iguais às do diário |
| `fClima_Albufeira.csv` | Volume e cota das albufeiras | Ano, Data, IDAlbufeira, IDAproveitamento, IDBacia, Indicador, Unidade, Valor, Fonte |
| `_Recolhas.csv` | Registo de cada execução do IPMA | Momento, Fonte, Indicador, LinhasNovas, PeriodoDe, PeriodoAte, Estado, Mensagem |
| `_Recolhas_SNIRH.csv` | Registo de cada execução do SNIRH | iguais às do `_Recolhas.csv` |

Regras de acumulação.

- A chave de cada linha é Data + Concelho (ou Albufeira) + Indicador. Correr a recolha duas vezes não duplica dados.
- Os meses completos com mais de 400 dias passam do diário para o mensal. A precipitação e a ET0 são somadas, as temperaturas ficam com a média dos valores diários.
- Nas albufeiras, os meses com mais de 400 dias ficam só com a última observação do mês, porque o armazenamento é um stock e não se soma.
- `IDConcelho` é o código DICO do INE e liga à `dConcelho`. `IDAlbufeira` liga à `dAlbufeira`.

## Acompanhamento

- **Estado de cada execução.** Abrir `dados/clima/_Recolhas.csv` (IPMA) e `dados/clima/_Recolhas_SNIRH.csv` (SNIRH). Os valores possíveis de `Estado` são `OK`, `ATRASO` (o IPMA não publica há mais de 3 dias), `PARCIAL`, `SEM DADOS` e `ERRO`.
- **Falhas do IPMA.** Se nenhum ficheiro do IPMA for recolhido, a execução falha e o GitHub envia um e-mail ao dono do repositório.
- **Falhas do SNIRH.** Ficam no `_Recolhas_SNIRH.csv` e no registo local do PC. Se não aparecer um commit «Clima SNIRH» durante vários dias, o PC não está a correr a tarefa (desligado, sem rede ou sem acesso ao GitHub).
- **ET0.** O IPMA deixou de publicar a ET0 em junho de 2026. Enquanto assim for, essa linha aparece com `ATRASO` todos os dias.

## Ligação ao Power BI

As tabelas `fClima_Diario`, `fClima_Mensal` e `fClima_Albufeira` do modelo devem ler os CSV deste repositório.

```
https://raw.githubusercontent.com/researchaee/obs-onr-26/main/dados/clima/fClima_Diario.csv
https://raw.githubusercontent.com/researchaee/obs-onr-26/main/dados/clima/fClima_Mensal.csv
https://raw.githubusercontent.com/researchaee/obs-onr-26/main/dados/clima/fClima_Albufeira.csv
```

As folhas com o mesmo nome no `ONR_Dados_Curados.xlsx` deixaram de ser atualizadas e ficam só como arquivo.

## Correr localmente

```bash
pip install requests openpyxl
python scripts/onr_clima_recolha.py --sem-snirh                                     # só IPMA (o que o GitHub corre)
python scripts/onr_clima_recolha.py --so-snirh --registo _Recolhas_SNIRH.csv        # só SNIRH (o que o PC corre)
python scripts/onr_clima_recolha.py --so-snirh --registo _Recolhas_SNIRH.csv --snirh-completo   # série completa do SNIRH
```

Outras opções: `--orcamento-snirh` (minutos máximos para o SNIRH, por omissão 20) e `--dias-ao-dia` (dias mantidos ao dia, por omissão 400).

