# Observatório Nacional do Regadio (ONR), 2.ª fase

Dados base do Observatório Nacional do Regadio e recolha automática da camada climática.

## Estrutura do repositório

| Caminho | O que é |
|---|---|
| `ONR_Dados_Curados.xlsx` | Livro curado com todas as tabelas do modelo (DGADR, IFAP, INE, Eurostat e dimensões). É mantido à mão pela equipa |
| `scripts/onr_clima_recolha.py` | Recolhedor da camada climática (IPMA e SNIRH) |
| `.github/workflows/clima-diario.yml` | Workflow do GitHub Actions que corre o recolhedor |
| `dados/clima/` | Dados de clima acumulados pelo recolhedor, em CSV |

## Fluxos automáticos

### Recolha diária de clima

O workflow **Recolha diária de clima (IPMA e SNIRH)** corre o `scripts/onr_clima_recolha.py` e grava o resultado em `dados/clima/` com um commit do `github-actions[bot]`. Se não houver dados novos, não faz commit.

Corre em três situações.

| Quando | Como |
|---|---|
| Todos os dias às 05:37 UTC | Automático (`schedule`) |
| À mão | Separador **Actions** → *Recolha diária de clima (IPMA e SNIRH)* → **Run workflow** |
| Quando o script ou o workflow são alterados no `main` | Automático (`push`) |

Na execução manual há a opção **Voltar a pedir ao SNIRH a série completa desde 1990**. Só é preciso usá-la se a série das albufeiras tiver ficado incompleta ou se se acrescentarem albufeiras novas com histórico.

### Fontes recolhidas

| Fonte | Dados | Grão | Histórico |
|---|---|---|---|
| IPMA, dados abertos | Precipitação, temperatura máxima, média e mínima, ET0 | dia × concelho | Só uma janela de 20 dias. A série acumula-se a partir da primeira recolha e os dias não recolhidos perdem-se |
| APA/SNIRH | Volume armazenado e cota | dia × albufeira | Desde 1990, trazido na primeira execução |

As albufeiras recolhidas são as da tabela `dAlbufeira` do `ONR_Dados_Curados.xlsx` que têm `SiteID_SNIRH` preenchido. Para acrescentar uma albufeira basta preencher esse campo no livro e fazer commit. A recolha seguinte traz a série completa dessa albufeira.

A água no solo do AgroClima não é recolhida, porque o IPMA não autorizou o uso desse serviço por terceiros.

## Dados produzidos

Todos os ficheiros estão em `dados/clima/`, em CSV UTF-8, separados por vírgula e com ponto decimal.

| Ficheiro | Conteúdo | Colunas |
|---|---|---|
| `fClima_Diario.csv` | Clima ao dia, últimos 400 dias | Ano, Data, IDConcelho, Indicador, Unidade, Valor, Dispersao, Fonte |
| `fClima_Mensal.csv` | Clima ao mês, meses completos mais antigos | iguais às do diário |
| `fClima_Albufeira.csv` | Volume e cota das albufeiras | Ano, Data, IDAlbufeira, IDAproveitamento, IDBacia, Indicador, Unidade, Valor, Fonte |
| `_Recolhas.csv` | Registo de cada execução | Momento, Fonte, Indicador, LinhasNovas, PeriodoDe, PeriodoAte, Estado, Mensagem |

Regras de acumulação.

- A chave de cada linha é Data + Concelho (ou Albufeira) + Indicador. Correr a recolha duas vezes não duplica dados.
- Os meses completos com mais de 400 dias passam do diário para o mensal. A precipitação e a ET0 são somadas, as temperaturas ficam com a média dos valores diários.
- Nas albufeiras, os meses com mais de 400 dias ficam só com a última observação do mês, porque o armazenamento é um stock e não se soma.
- `IDConcelho` é o código DICO do INE e liga à `dConcelho`. `IDAlbufeira` liga à `dAlbufeira`.

## Acompanhamento

- **Estado de cada execução.** Abrir `dados/clima/_Recolhas.csv`. Os valores possíveis de `Estado` são `OK`, `ATRASO` (o IPMA não publica há mais de 3 dias), `PARCIAL`, `SEM DADOS` e `ERRO`.
- **Falhas.** Se nenhum ficheiro do IPMA for recolhido, a execução falha e o GitHub envia um e-mail ao dono do repositório. Uma falha só do SNIRH fica registada no `_Recolhas.csv` sem falhar a execução.
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
python scripts/onr_clima_recolha.py                    # recolha normal
python scripts/onr_clima_recolha.py --snirh-completo   # série completa do SNIRH
python scripts/onr_clima_recolha.py --sem-snirh        # só IPMA
python scripts/onr_clima_recolha.py --dias-ao-dia 180  # muda o número de dias mantidos ao dia
```
