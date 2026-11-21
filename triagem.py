"""
Triagem de candidatos por compatibilidade ponderada.

Critérios desejáveis podem ser:
  - sim/não: vale o peso inteiro ou nada
  - graduais: têm "faixas" e o candidato ganha peso x fator

Uso:
    python triagem.py
    python triagem.py --criterios criterios.json --candidatos candidatos.csv --saida ranking.xlsx
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

VERDADEIROS = {"sim", "s", "true", "1", "yes", "y"}


# ---------------------------------------------------------------- leitura
def carregar_criterios(caminho):
    """Lê o JSON de critérios e valida a estrutura, os pesos e as faixas."""
    with open(caminho, encoding="utf-8") as f:
        criterios = json.load(f)

    ids = [c["id"] for c in criterios]
    if len(ids) != len(set(ids)):
        raise ValueError("Há critérios com 'id' repetido.")

    for c in criterios:
        if c["tipo"] not in ("eliminatorio", "desejavel"):
            raise ValueError(f"Tipo inválido no critério '{c['id']}': {c['tipo']}")
        if c["tipo"] == "desejavel" and "peso" not in c:
            raise ValueError(f"O critério desejável '{c['id']}' precisa de 'peso'.")
        for faixa in c.get("faixas", []):
            if not 0 <= faixa["fator"] <= 1:
                raise ValueError(
                    f"Na faixa de '{c['id']}', o fator deve estar entre 0 e 1."
                )

    soma = sum(c["peso"] for c in criterios if c["tipo"] == "desejavel")
    if soma != 100:
        print(f"Aviso: os pesos somam {soma}, não 100. O percentual será "
              f"calculado proporcionalmente.", file=sys.stderr)

    return criterios


def carregar_candidatos(caminho, criterios):
    """Lê CSV ou Excel com pandas e converte cada coluna conforme o critério.

    - Critério gradual (com faixas): coluna numérica (ex.: anos de experiência)
    - Critério sim/não: coluna convertida para True/False
    """
    caminho = Path(caminho)
    if caminho.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(caminho)
    else:
        df = pd.read_csv(caminho, encoding="utf-8")

    faltando = [c for c in ["nome", *[c["id"] for c in criterios]]
                if c not in df.columns]
    if faltando:
        raise ValueError(f"Colunas ausentes no arquivo de candidatos: {faltando}")

    for c in criterios:
        col = c["id"]
        if c.get("faixas"):
            # Números. Vazio ou texto vira 0 em vez de quebrar o programa.
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        else:
            # O arquivo entrega texto. Sem esta conversão, "nao" seria tratado
            # como verdadeiro (toda string não vazia é True em Python).
            df[col] = df[col].astype(str).str.strip().str.lower().isin(VERDADEIROS)

    return df


# ---------------------------------------------------------------- cálculo
def fator_do_criterio(criterio, valor):
    """Converte o valor do candidato em um fator entre 0 e 1."""
    faixas = criterio.get("faixas")

    if not faixas:                      # critério sim/não
        return 1.0 if valor else 0.0

    fator = 0.0
    for f in sorted(faixas, key=lambda f: f["minimo"]):
        if valor >= f["minimo"]:
            fator = f["fator"]          # guarda a maior faixa atingida
    return fator


def calcular_compatibilidade(candidato, criterios):
    pontos, total = 0, 0
    atendidos, parciais, faltantes = [], [], []

    for c in criterios:
        if c["tipo"] == "eliminatorio" and not candidato.get(c["id"]):
            return {"percentual": 0, "eliminado": True,
                    "motivo": f"Não atende: {c['nome']}",
                    "atendidos": [], "parciais": [], "faltantes": []}

        if c["tipo"] == "desejavel":
            total += c["peso"]
            fator = fator_do_criterio(c, candidato.get(c["id"], 0))
            pontos += c["peso"] * fator

            if fator == 1:
                atendidos.append(c["nome"])
            elif fator > 0:
                parciais.append(f"{c['nome']} ({round(fator * 100)}%)")
            else:
                faltantes.append(c["nome"])

    return {"percentual": round(pontos / total * 100) if total else 0,
            "eliminado": False, "motivo": "",
            "atendidos": atendidos, "parciais": parciais, "faltantes": faltantes}


def gerar_ranking(df, criterios):
    linhas = []
    for candidato in df.to_dict(orient="records"):
        r = calcular_compatibilidade(candidato, criterios)
        linhas.append({
            "Nome": candidato["nome"],
            "Compatibilidade (%)": r["percentual"],
            "Situação": "Eliminado" if r["eliminado"] else "Elegível",
            "Motivo / Critérios que faltam": (
                r["motivo"] if r["eliminado"] else "; ".join(r["faltantes"]) or "Nenhum"
            ),
            "Atendimento parcial": "; ".join(r["parciais"]),
            "Critérios atendidos": "; ".join(r["atendidos"]),
        })

    ranking = pd.DataFrame(linhas)
    ranking["_elim"] = ranking["Situação"] == "Eliminado"
    ranking = (ranking
               .sort_values(["_elim", "Compatibilidade (%)"], ascending=[True, False])
               .drop(columns="_elim")
               .reset_index(drop=True))
    ranking.index += 1
    ranking.index.name = "Posição"
    return ranking


# ---------------------------------------------------------------- execução
def main():
    p = argparse.ArgumentParser(description="Triagem de candidatos")
    p.add_argument("--criterios", default="criterios.json")
    p.add_argument("--candidatos", default="candidatos.csv")
    p.add_argument("--saida", default="ranking.xlsx")
    args = p.parse_args()

    criterios = carregar_criterios(args.criterios)
    df = carregar_candidatos(args.candidatos, criterios)
    ranking = gerar_ranking(df, criterios)

    pd.set_option("display.width", 200)
    pd.set_option("display.max_colwidth", 60)
    print(ranking[["Nome", "Compatibilidade (%)", "Situação",
                   "Atendimento parcial", "Motivo / Critérios que faltam"]].to_string())

    ranking.to_excel(args.saida)
    print(f"\nRanking salvo em: {args.saida}")
    print("Lembrete: o percentual apoia a decisão, quem decide é o recrutador.")


if __name__ == "__main__":
    main()