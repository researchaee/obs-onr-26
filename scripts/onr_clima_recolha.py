"""Recolhedor da camada climática do Observatório Nacional do Regadio.

Corre no GitHub Actions (ver .github/workflows/clima-diario.yml) e também à mão:

    python scripts/onr_clima_recolha.py               # recolha diária
    python scripts/onr_clima_recolha.py --snirh-completo

Fontes
  IPMA  dados abertos, janela de 20 dias por concelho (precipitação, temperatura, ET0).
        Não há histórico, por isso a série acumula-se aqui a partir do primeiro dia de recolha.
  SNIRH volume armazenado e cota das albufeiras da dAlbufeira, série desde 1990.

Saídas (CSV UTF-8, separador vírgula, ponto decimal), em dados/clima/
  fClima_Diario.csv     dia x concelho x indicador, últimos N dias (por omissão 400)
  fClima_Mensal.csv     mês x concelho x indicador, meses completos mais antigos que isso
  fClima_Albufeira.csv  albufeira x indicador; diário recente, último valor do mês no histórico
  _Recolhas.csv         registo de cada execução

Idempotente. A chave é Data + Concelho/Albufeira + Indicador; correr duas vezes não duplica.
A água no solo do AgroClima não está incluída (endpoint sem autorização de uso por terceiros).
"""
from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import io
import os
import re
import shutil
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent.parent
PASTA = RAIZ / "dados" / "clima"
LIVRO = RAIZ / "ONR_Dados_Curados.xlsx"

COLS_CLIMA = ["Ano", "Data", "IDConcelho", "Indicador", "Unidade", "Valor", "Dispersao", "Fonte"]
COLS_ALB = ["Ano", "Data", "IDAlbufeira", "IDAproveitamento", "IDBacia", "Indicador", "Unidade", "Valor", "Fonte"]
COLS_REG = ["Momento", "Fonte", "Indicador", "LinhasNovas", "PeriodoDe", "PeriodoAte", "Estado", "Mensagem"]

IPMA_BASE = "https://api.ipma.pt/open-data/observation/climate/"
# ficheiro -> pastas candidatas (a primeira que responder é usada)
IPMA_FICHEIROS = {
    "prec-p1d-continental-obssup-idw-concelhos-20d.csv": ["precipitation"],
    "t2m-p1d-continental-obssup-idw-concelhos-20d.csv": ["temperature"],
    "et0-p1d-continental-obssup-idw-concelhos-20d.csv": ["evapotranspiration", "et0", "evapotranspiracao"],
}
# coluna do CSV -> (indicador, unidade)
IPMA_VARIAVEIS = {
    "mean_tp": ("Precipitação", "mm"),
    "mean_maxt2m": ("Temperatura máxima", "°C"),
    "mean_meant2m": ("Temperatura média", "°C"),
    "mean_mint2m": ("Temperatura mínima", "°C"),
    "mean_et0": ("ET0", "mm"),
}
SOMA_MENSAL = {"Precipitação", "ET0"}  # restantes: média dos valores diários

SNIRH_URL = "https://snirh.apambiente.pt/snirh/_dadosbase/site/paraCSV/dados_csv.php"
SNIRH_PARAMETROS = {
    "1629599798": ("Volume armazenado", "dam3"),
    "1629599726": ("Cota", "m"),
}
SNIRH_BLOCOS = [(date(1990, 1, 1), date(2000, 12, 31)), (date(2001, 1, 1), date(2010, 12, 31))]

DIAS_ATRASO_ALERTA = 3
HEADERS = {"User-Agent": "ONR-recolha-clima/1.0 (Observatorio Nacional do Regadio; GitHub Actions)"}


# ---------------------------------------------------------------- utilitários

def ler_csv(caminho: Path, colunas: list[str]) -> list[dict]:
    if not caminho.exists():
        return []
    with caminho.open(encoding="utf-8", newline="") as f:
        return [dict(r) for r in csv.DictReader(f)]


def gravar_csv(caminho: Path, colunas: list[str], linhas: list[dict]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=colunas, lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        w.writerows(linhas)
    tmp.replace(caminho)


def num(txt) -> str:
    """Normaliza um número para texto com ponto decimal; '' se vazio."""
    if txt is None:
        return ""
    t = str(txt).strip().replace(" ", "")
    if t == "" or t.lower() in {"nan", "null", "none", "-"}:
        return ""
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".")
    elif "," in t:
        t = t.replace(",", ".")
    try:
        v = float(t)
    except ValueError:
        return ""
    return f"{v:.6f}".rstrip("0").rstrip(".") if v != int(v) else str(int(v))


def get(url: str, tentativas: int = 3, timeout: int = 90, **kw) -> requests.Response:
    ultimo = None
    for tentativa in range(tentativas):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout, **kw)
            if r.status_code == 200:
                return r
            ultimo = f"HTTP {r.status_code}"
            if r.status_code == 404:
                break
        except requests.RequestException as e:  # rede
            ultimo = str(e)[:200]
        if tentativa < tentativas - 1:
            time.sleep(5 * (tentativa + 1))
    raise RuntimeError(ultimo or "sem resposta")


# ---------------------------------------------------------------- IPMA

def recolher_ipma(diario: dict, registo: list, agora: str) -> bool:
    ok_algum = False
    for ficheiro, pastas in IPMA_FICHEIROS.items():
        resp, erro = None, None
        for pasta in pastas:
            try:
                resp = get(IPMA_BASE + pasta + "/" + ficheiro)
                break
            except RuntimeError as e:
                erro = f"{pasta}/: {e}"
        if resp is None:
            registo.append(dict(Momento=agora, Fonte="IPMA", Indicador=ficheiro, LinhasNovas=0,
                                Estado="ERRO", Mensagem=erro))
            continue
        try:
            leitor = csv.DictReader(io.StringIO(resp.content.decode("utf-8-sig")))
            novas, datas = 0, []
            for r in leitor:
                t = (r.get("time") or r.get("date") or "").strip()[:10]
                zid = (r.get("zid") or r.get("dico") or "").strip()
                if not t or not zid:
                    continue
                d = date.fromisoformat(t)
                idc = str(int(float(zid)))
                for col, (ind, uni) in IPMA_VARIAVEIS.items():
                    if col not in r:
                        continue
                    valor = num(r[col])
                    if valor == "":
                        continue
                    disp = num(r.get("std_" + col[5:], ""))
                    chave = (d.isoformat(), idc, ind)
                    if chave not in diario:
                        novas += 1
                    diario[chave] = dict(Ano=d.year, Data=d.isoformat(), IDConcelho=idc, Indicador=ind,
                                         Unidade=uni, Valor=valor, Dispersao=disp, Fonte="IPMA")
                    datas.append(d)
            if not datas:
                raise RuntimeError("ficheiro sem linhas reconhecíveis (colunas: "
                                   + ", ".join(leitor.fieldnames or []) + ")")
            ate = max(datas)
            atraso = (date.today() - ate).days
            estado = "OK" if atraso <= DIAS_ATRASO_ALERTA else "ATRASO"
            msg = None if estado == "OK" else f"último dia publicado pelo IPMA tem {atraso} dias"
            registo.append(dict(Momento=agora, Fonte="IPMA", Indicador=ficheiro, LinhasNovas=novas,
                                PeriodoDe=min(datas).isoformat(), PeriodoAte=ate.isoformat(),
                                Estado=estado, Mensagem=msg))
            ok_algum = True
        except Exception as e:  # formato inesperado
            registo.append(dict(Momento=agora, Fonte="IPMA", Indicador=ficheiro, LinhasNovas=0,
                                Estado="ERRO", Mensagem=str(e)[:300]))
    return ok_algum


def compactar(diario: dict, mensal: dict, dias_ao_dia: int) -> int:
    """Move para o mensal os meses completos anteriores ao corte. Devolve linhas movidas."""
    corte = date.today() - timedelta(days=dias_ao_dia)
    primeiro_mes_mantido = date(corte.year, corte.month, 1)
    grupos = defaultdict(list)
    for chave, r in list(diario.items()):
        d = date.fromisoformat(r["Data"])
        if d < primeiro_mes_mantido:
            grupos[(d.year, d.month, r["IDConcelho"], r["Indicador"], r["Unidade"], r["Fonte"])].append(r)
            del diario[chave]
    movidas = 0
    for (a, m, idc, ind, uni, fonte), rs in grupos.items():
        vals = [float(r["Valor"]) for r in rs if r["Valor"] != ""]
        if not vals:
            continue
        v = sum(vals) if ind in SOMA_MENSAL else sum(vals) / len(vals)
        d1 = date(a, m, 1).isoformat()
        mensal[(d1, idc, ind)] = dict(Ano=a, Data=d1, IDConcelho=idc, Indicador=ind, Unidade=uni,
                                      Valor=num(round(v, 3)), Dispersao="", Fonte=fonte)
        movidas += len(rs)
    return movidas


# ---------------------------------------------------------------- SNIRH

def ler_albufeiras() -> list[dict]:
    from openpyxl import load_workbook

    wb = load_workbook(LIVRO, read_only=True, data_only=True)
    ws = wb["dAlbufeira"]
    linhas = ws.iter_rows(values_only=True)
    cab = [str(c) if c is not None else "" for c in next(linhas)]
    out = []
    for r in linhas:
        reg = dict(zip(cab, r))
        if reg.get("IDAlbufeira") is None or not reg.get("SiteID_SNIRH"):
            continue
        out.append(reg)
    wb.close()
    return out


RE_LINHA = re.compile(r'^\s*"?(\d{2})/(\d{2})/(\d{4})(?:\s+\d{2}:\d{2}(?::\d{2})?)?"?\s*[,;\t]\s*"?([-\d.,]+)')


def pedir_snirh(site: str, par: str, de: date, ate: date) -> list[tuple[date, str]]:
    resp = get(SNIRH_URL, tentativas=2, timeout=40, params=dict(sites=site, pars=par, tmin=de.strftime("%d/%m/%Y"),
                                      tmax=ate.strftime("%d/%m/%Y"), formato="csv"))
    texto = resp.content.decode("iso-8859-1")
    out = []
    for linha in texto.splitlines():
        m = RE_LINHA.match(linha)
        if not m:
            continue
        valor = num(m.group(4).rstrip(",;"))
        if valor == "":
            continue
        out.append((date(int(m.group(3)), int(m.group(2)), int(m.group(1))), valor))
    return out


def partir_em_blocos(de: date, ate: date, anos: int = 5) -> list[tuple[date, date]]:
    """Pedidos grandes ao SNIRH dão HTTP 500; parte o intervalo em blocos de no máximo 5 anos."""
    blocos = []
    while de <= ate:
        fim = min(date(de.year + anos, 1, 1) - timedelta(days=1), ate)
        blocos.append((de, fim))
        de = fim + timedelta(days=1)
    return blocos


def recolher_snirh(alb: dict, registo: list, agora: str, completo: bool, orcamento_min: float) -> bool:
    try:
        albufeiras = ler_albufeiras()
    except Exception as e:
        registo.append(dict(Momento=agora, Fonte="SNIRH", Indicador="dAlbufeira", LinhasNovas=0,
                            Estado="ERRO", Mensagem=f"não consegui ler a dAlbufeira: {e}"[:300]))
        return False
    hoje = date.today()
    ultima = defaultdict(lambda: None)
    for r in alb.values():
        k = (r["IDAlbufeira"], r["Indicador"])
        d = date.fromisoformat(r["Data"])
        if ultima[k] is None or d > ultima[k]:
            ultima[k] = d
    ok_algum = False
    inicio = time.monotonic()
    falhas_seguidas = 0
    for a in albufeiras:
        if time.monotonic() - inicio > orcamento_min * 60:
            registo.append(dict(Momento=agora, Fonte="SNIRH", Indicador="interrompido", LinhasNovas=0,
                                Estado="PARCIAL", Mensagem=f"orçamento de {orcamento_min:g} min esgotado; "
                                "continua na próxima execução"))
            break
        if falhas_seguidas >= 4:
            registo.append(dict(Momento=agora, Fonte="SNIRH", Indicador="interrompido", LinhasNovas=0,
                                Estado="ERRO", Mensagem="4 pedidos seguidos sem resposta; SNIRH inacessível "
                                "a partir do GitHub nesta execução"))
            break
        ida = str(a["IDAlbufeira"])
        site = str(a["SiteID_SNIRH"]).strip()
        for par, (ind, uni) in SNIRH_PARAMETROS.items():
            ult = ultima[(ida, ind)]
            inicio_pedido = date(1990, 1, 1) if (completo or ult is None) else ult - timedelta(days=10)
            blocos = partir_em_blocos(inicio_pedido, hoje)
            pontos, erros = [], []
            for de, ate in blocos:
                try:
                    pontos += pedir_snirh(site, par, de, ate)
                    falhas_seguidas = 0
                except RuntimeError as e:
                    erros.append(f"{de.year}-{ate.year}: {e}")
                    falhas_seguidas += 1
                    if falhas_seguidas >= 4:
                        break
                time.sleep(0.5)
            print(f"SNIRH {a.get('Albufeira')} · {ind}: {len(pontos)} pontos"
                  + (f" ({'; '.join(erros)})" if erros else ""), flush=True)
            novas = 0
            for d, v in pontos:
                chave = (d.isoformat(), ida, ind)
                if chave not in alb:
                    novas += 1
                alb[chave] = dict(Ano=d.year, Data=d.isoformat(), IDAlbufeira=ida,
                                  IDAproveitamento=a.get("IDAproveitamento") or "",
                                  IDBacia=a.get("IDBacia") or "", Indicador=ind, Unidade=uni,
                                  Valor=v, Fonte="APA/SNIRH")
            if pontos:
                ok_algum = True
                estado = "OK" if not erros else "PARCIAL"
            else:
                estado = "ERRO" if erros else "SEM DADOS"
            registo.append(dict(Momento=agora, Fonte="SNIRH",
                                Indicador=f"{a.get('Albufeira')} ({site}) · {ind}", LinhasNovas=novas,
                                PeriodoDe=min(p[0] for p in pontos).isoformat() if pontos else None,
                                PeriodoAte=max(p[0] for p in pontos).isoformat() if pontos else None,
                                Estado=estado, Mensagem="; ".join(erros)[:300] or None))
    return ok_algum


def compactar_albufeiras(alb: dict, dias_ao_dia: int) -> int:
    """Nos meses completos anteriores ao corte fica só a última observação do mês (é um stock)."""
    corte = date.today() - timedelta(days=dias_ao_dia)
    primeiro_mes_mantido = date(corte.year, corte.month, 1)
    ultimo = {}
    for chave, r in alb.items():
        d = date.fromisoformat(r["Data"])
        if d >= primeiro_mes_mantido:
            continue
        g = (d.year, d.month, r["IDAlbufeira"], r["Indicador"])
        if g not in ultimo or d > date.fromisoformat(alb[ultimo[g]]["Data"]):
            ultimo[g] = chave
    manter = set(ultimo.values())
    removidas = 0
    for chave in list(alb):
        d = date.fromisoformat(alb[chave]["Data"])
        if d < primeiro_mes_mantido and chave not in manter:
            del alb[chave]
            removidas += 1
    return removidas


# ---------------------------------------------------------------- livro curado (SharePoint -> GitHub)

# O original vive no SharePoint e é o que o Power BI lê. No PC, a biblioteca está sincronizada pelo
# OneDrive; a cópia do repositório é um espelho, atualizado aqui, e nunca se edita à mão.
PADRAO_SHAREPOINT = os.path.join(
    os.path.expanduser("~"), "OneDrive - CONSULAI", "01_Atalhos",
    "*011_FENAREG_COTR_Observatorio_Nacional_Regadio", "Trabalho", "04.2* Fase",
    "04.Dados", "01.Curados", "ONR_Dados_Curados.xlsx")


def _sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def espelhar_livro(origem: str | None, registo: list, agora: str) -> None:
    """Copia o livro curado do SharePoint sincronizado para o repositório, se tiver mudado."""
    if not origem:
        encontrados = glob.glob(os.environ.get("ONR_LIVRO_SHAREPOINT") or PADRAO_SHAREPOINT)
        origem = encontrados[0] if encontrados else None
    if not origem or not os.path.exists(origem):
        registo.append(dict(Momento=agora, Fonte="ONR", Indicador="livro curado", LinhasNovas=0, Estado="ERRO",
                            Mensagem="não encontrei a cópia sincronizada do SharePoint; usei a do repositório"))
        return
    try:
        if LIVRO.exists() and _sha256(Path(origem)) == _sha256(LIVRO):
            return
        shutil.copyfile(origem, LIVRO)
        registo.append(dict(Momento=agora, Fonte="ONR", Indicador="livro curado", LinhasNovas=0, Estado="OK",
                            Mensagem="cópia do repositório atualizada a partir do SharePoint"))
    except OSError as e:  # ficheiro bloqueado ou só na nuvem
        registo.append(dict(Momento=agora, Fonte="ONR", Indicador="livro curado", LinhasNovas=0, Estado="ERRO",
                            Mensagem=f"não consegui copiar do SharePoint: {e}"[:300]))


# ---------------------------------------------------------------- principal

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--snirh-completo", action="store_true", help="volta a pedir ao SNIRH a série desde 1990")
    ap.add_argument("--sem-snirh", action="store_true", help="só IPMA")
    ap.add_argument("--so-snirh", action="store_true", help="só SNIRH")
    ap.add_argument("--orcamento-snirh", type=float, default=20, help="minutos máximos para o SNIRH (por omissão 20)")
    ap.add_argument("--registo", default="_Recolhas.csv",
                    help="ficheiro de registo em dados/clima (o PC usa _Recolhas_SNIRH.csv)")
    ap.add_argument("--espelhar-livro", action="store_true",
                    help="atualiza a cópia do livro curado no repositório a partir do SharePoint sincronizado")
    ap.add_argument("--livro-sharepoint", help="caminho do livro no SharePoint sincronizado (por omissão procura-o)")
    ap.add_argument("--dias-ao-dia", type=int, default=400, help="dias mantidos ao dia (por omissão 400)")
    args = ap.parse_args()

    agora = datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None).isoformat() + "Z"
    f_dia, f_mes = PASTA / "fClima_Diario.csv", PASTA / "fClima_Mensal.csv"
    f_alb, f_reg = PASTA / "fClima_Albufeira.csv", PASTA / args.registo

    diario = {(r["Data"], r["IDConcelho"], r["Indicador"]): r for r in ler_csv(f_dia, COLS_CLIMA)}
    mensal = {(r["Data"], r["IDConcelho"], r["Indicador"]): r for r in ler_csv(f_mes, COLS_CLIMA)}
    alb = {(r["Data"], r["IDAlbufeira"], r["Indicador"]): r for r in ler_csv(f_alb, COLS_ALB)}
    registo: list[dict] = []
    if args.espelhar_livro:
        espelhar_livro(args.livro_sharepoint, registo, agora)

    ok_ipma = True
    if not args.so_snirh:
        ok_ipma = recolher_ipma(diario, registo, agora)
        movidas = compactar(diario, mensal, args.dias_ao_dia)
        if movidas:
            registo.append(dict(Momento=agora, Fonte="ONR", Indicador="compactação diário → mensal",
                                LinhasNovas=movidas, Estado="OK"))

    ok_snirh = True
    if not args.sem_snirh:
        ok_snirh = recolher_snirh(alb, registo, agora, args.snirh_completo, args.orcamento_snirh)
        compactar_albufeiras(alb, args.dias_ao_dia)

    ordem = lambda r: (r["Data"], int(r.get("IDConcelho") or r.get("IDAlbufeira") or 0), r["Indicador"])
    # cada execução só grava o que recolheu: o IPMA (GitHub) e o SNIRH (PC) nunca tocam no mesmo ficheiro
    if not args.so_snirh:
        gravar_csv(f_dia, COLS_CLIMA, sorted(diario.values(), key=ordem))
        gravar_csv(f_mes, COLS_CLIMA, sorted(mensal.values(), key=ordem))
    if not args.sem_snirh:
        gravar_csv(f_alb, COLS_ALB, sorted(alb.values(), key=ordem))
    gravar_csv(f_reg, COLS_REG, ler_csv(f_reg, COLS_REG) + registo)

    for r in registo:
        print(f"{r['Fonte']:6} {r.get('Estado',''):9} +{r.get('LinhasNovas',0):>6}  {r['Indicador']}"
              + (f"  [{r['Mensagem']}]" if r.get("Mensagem") else ""))

    # Falha (e o GitHub envia e-mail) se o IPMA falhar por completo, porque cada dia perdido não volta.
    if not ok_ipma:
        print("ERRO: nenhum ficheiro do IPMA foi recolhido.", file=sys.stderr)
        return 1
    if not ok_snirh:
        print("AVISO: o SNIRH não devolveu dados nesta execução.", file=sys.stderr)
        if args.so_snirh:
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
