Ficheiro de dados base do Observatório Nacional do Regadio 

## Recolha automática de clima

O workflow `.github/workflows/clima-diario.yml` corre todos os dias às 05:37 UTC o
`scripts/onr_clima_recolha.py`, que vai buscar ao IPMA (precipitação, temperatura, ET0) e ao
SNIRH (volume armazenado e cota das albufeiras da `dAlbufeira`) e acumula os dados em
`dados/clima/`. O registo de cada execução fica em `dados/clima/_Recolhas.csv`.

Para correr à mão: separador **Actions** → *Recolha diária de clima* → **Run workflow**.
