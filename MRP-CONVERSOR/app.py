import io
import re
from datetime import datetime
from typing import Iterable

import pandas as pd
import streamlit as st

st.set_page_config(page_title="MRP • Conversor de Relatórios", page_icon="📊", layout="wide")

APP_VERSION = "0.1.0"
REQUIRED_COLUMNS = {
    "Projeto",
    "Código",
    "Última solicitação",
    "Qtd. necessária",
    "Qtd. atendida",
    "Resp. separação",
    "Data de separação",
    "Resp. conferência",
    "Data de conferência",
}


def normalize_code(value, width: int) -> str:
    """Normaliza códigos numéricos/textuais, completando zeros à esquerda."""
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if re.fullmatch(r"\d+\.0", text):
        text = text[:-2]
    digits = re.sub(r"\D", "", text)
    return digits.zfill(width) if digits else ""


def unique_names(values: Iterable) -> str:
    seen = []
    for value in values:
        if pd.isna(value):
            continue
        text = str(value).strip()
        if not text or text.lower() in {"nan", "none"}:
            continue
        if text not in seen:
            seen.append(text)
    return "; ".join(seen)


def max_date(values, dayfirst=True):
    parsed = pd.to_datetime(pd.Series(values), errors="coerce", dayfirst=dayfirst)
    if parsed.notna().any():
        return parsed.max()
    return pd.NaT


def format_date(value):
    if pd.isna(value):
        return ""
    return pd.Timestamp(value).strftime("%d/%m/%Y")


def format_datetime(value):
    if pd.isna(value):
        return ""
    return pd.Timestamp(value).strftime("%d/%m/%Y %H:%M")


def read_excel(uploaded_file) -> pd.DataFrame:
    return pd.read_excel(uploaded_file, sheet_name=0, dtype=object)


def validate_source(df: pd.DataFrame):
    normalized = {str(c).strip() for c in df.columns}
    missing = sorted(REQUIRED_COLUMNS - normalized)
    return missing


def prepare_source(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df


def transform_relatorio_geral(df: pd.DataFrame):
    """Consolida o RelatorioGeral em uma linha por Projeto + Código.

    Regras v1:
    - Projeto: 11 dígitos.
    - Código: 8 dígitos.
    - COD_MRP = Projeto_00000000.
    - Última solicitação: maior data do grupo.
    - Qtd. necessária: soma.
    - Qtd. atendida: soma.
    - Pendência: necessária - atendida.
    - Responsáveis: todos os nomes distintos.
    - Data de separação/conferência: maior data do grupo.
    - Lote não participa da chave nem da consolidação nesta versão.
    """
    src = prepare_source(df)

    for col in ["Projeto", "Código"]:
        if col not in src.columns:
            raise ValueError(f"Coluna obrigatória ausente: {col}")

    src["PROJETO_PADRAO"] = src["Projeto"].apply(lambda x: normalize_code(x, 11))
    src["CODIGO_PADRAO"] = src["Código"].apply(lambda x: normalize_code(x, 8))
    src["COD_MRP"] = src["PROJETO_PADRAO"] + "_" + src["CODIGO_PADRAO"]

    src["QTD_NECESSARIA_NUM"] = pd.to_numeric(src.get("Qtd. necessária"), errors="coerce").fillna(0)
    src["QTD_ATENDIDA_NUM"] = pd.to_numeric(src.get("Qtd. atendida"), errors="coerce").fillna(0)

    src["DATA_SOLICITACAO_DT"] = pd.to_datetime(src.get("Última solicitação"), errors="coerce", dayfirst=True)
    src["DATA_SEPARACAO_DT"] = pd.to_datetime(src.get("Data de separação"), errors="coerce", dayfirst=True)
    src["DATA_CONFERENCIA_DT"] = pd.to_datetime(src.get("Data de conferência"), errors="coerce", dayfirst=True)

    invalid_project = src["PROJETO_PADRAO"].eq("") | (src["PROJETO_PADRAO"].str.len() != 11)
    invalid_code = src["CODIGO_PADRAO"].eq("") | (src["CODIGO_PADRAO"].str.len() != 8)

    group_cols = ["COD_MRP"]
    rows = []

    for key, group in src.groupby(group_cols, dropna=False, sort=False):
        projeto = group["PROJETO_PADRAO"].iloc[0]
        codigo = group["CODIGO_PADRAO"].iloc[0]

        # Descrição e demais atributos descritivos: primeira informação não vazia.
        def first_nonempty(col):
            if col not in group.columns:
                return ""
            for v in group[col]:
                if not pd.isna(v) and str(v).strip():
                    return str(v).strip()
            return ""

        necessidade = float(group["QTD_NECESSARIA_NUM"].sum())
        atendida = float(group["QTD_ATENDIDA_NUM"].sum())
        pendencia = necessidade - atendida

        row = {
            "COD_MRP": str(key[0]),
            "PROJETO": projeto,
            "CODIGO_PRODUTO": codigo,
            "DESCRICAO": first_nonempty("Descrição"),
            "PA": first_nonempty("P.A."),
            "DESCRICAO_PA": first_nonempty("Descrição P.A."),
            "ULTIMA_SOLICITACAO": format_date(group["DATA_SOLICITACAO_DT"].max()),
            "QTD_NECESSARIA": necessidade,
            "QTD_ATENDIDA": atendida,
            "PENDENCIA": pendencia,
            "RESPONSAVEL_SEPARACAO": unique_names(group["Resp. separação"]),
            "DATA_ULTIMA_SEPARACAO": format_datetime(group["DATA_SEPARACAO_DT"].max()),
            "RESPONSAVEL_CONFERENCIA": unique_names(group["Resp. conferência"]),
            "DATA_ULTIMA_CONFERENCIA": format_datetime(group["DATA_CONFERENCIA_DT"].max()),
            "QTD_LINHAS_ORIGINAIS": int(len(group)),
        }
        rows.append(row)

    result = pd.DataFrame(rows)

    if not result.empty:
        result["QTD_NECESSARIA"] = result["QTD_NECESSARIA"].round(6)
        result["QTD_ATENDIDA"] = result["QTD_ATENDIDA"].round(6)
        result["PENDENCIA"] = result["PENDENCIA"].round(6)

    validation = {
        "linhas_originais": len(src),
        "linhas_tratadas": len(result),
        "linhas_agrupadas": int(len(src) - len(result)),
        "chaves_unicas": int(result["COD_MRP"].nunique()) if not result.empty else 0,
        "projetos_invalidos": int(invalid_project.sum()),
        "codigos_invalidos": int(invalid_code.sum()),
        "projetos_unicos": int(result["PROJETO"].nunique()) if not result.empty else 0,
        "materiais_unicos": int(result["CODIGO_PRODUTO"].nunique()) if not result.empty else 0,
        "pendencias_positivas": int((result["PENDENCIA"] > 0).sum()) if not result.empty else 0,
        "atendimentos_acima_necessidade": int((result["PENDENCIA"] < 0).sum()) if not result.empty else 0,
    }
    return result, validation


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Relatorio_Tratado")
    return output.getvalue()


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")


st.title("Conversor de Relatórios MRP")
st.caption(f"Versão {APP_VERSION} • Primeiro conversor: RelatorioGeral")

with st.sidebar:
    st.header("Relatórios")
    report_type = st.selectbox("Tipo de relatório", ["RelatorioGeral"])
    st.divider()
    st.markdown("**Regra atual**")
    st.write("Uma linha por Projeto + Código.")
    st.write("Projeto = 11 dígitos; Código = 8 dígitos.")
    st.write("Lote não participa da chave nesta versão.")

uploaded = st.file_uploader("Envie o relatório bruto", type=["xlsx", "xls"], accept_multiple_files=False)

if not uploaded:
    st.info("Envie o RelatorioGeral bruto para iniciar a transformação.")
    st.stop()

try:
    source = read_excel(uploaded)
except Exception as exc:
    st.error(f"Não foi possível ler o arquivo: {exc}")
    st.stop()

missing = validate_source(source)
if missing:
    st.error("O relatório não possui todas as colunas obrigatórias.")
    st.write("Colunas ausentes:", missing)
    st.write("Colunas encontradas:", list(source.columns))
    st.stop()

st.success(f"Arquivo carregado: {uploaded.name} • {len(source):,} linhas")

if st.button("Processar relatório", type="primary", use_container_width=True):
    try:
        treated, metrics = transform_relatorio_geral(source)
        st.session_state["treated"] = treated
        st.session_state["metrics"] = metrics
        st.session_state["source_name"] = uploaded.name
        st.session_state["processed_at"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    except Exception as exc:
        st.exception(exc)

if "treated" not in st.session_state:
    st.stop()

treated = st.session_state["treated"]
metrics = st.session_state["metrics"]

st.subheader("Conferência da transformação")
cols = st.columns(6)
cols[0].metric("Linhas originais", f"{metrics['linhas_originais']:,}")
cols[1].metric("Linhas tratadas", f"{metrics['linhas_tratadas']:,}")
cols[2].metric("Agrupadas", f"{metrics['linhas_agrupadas']:,}")
cols[3].metric("Projetos", f"{metrics['projetos_unicos']:,}")
cols[4].metric("Materiais", f"{metrics['materiais_unicos']:,}")
cols[5].metric("Pendências", f"{metrics['pendencias_positivas']:,}")

if metrics["projetos_invalidos"] or metrics["codigos_invalidos"]:
    st.warning(
        f"Foram identificados {metrics['projetos_invalidos']} projetos fora do padrão e "
        f"{metrics['codigos_invalidos']} códigos fora do padrão. A validação não deve ser considerada concluída."
    )
else:
    st.success("Projeto e Código estão padronizados na saída.")

st.write(f"Processado em {st.session_state['processed_at']}")

st.subheader("Dados tratados")
st.dataframe(treated, use_container_width=True, height=520)

c1, c2 = st.columns(2)
with c1:
    st.download_button(
        "Baixar Excel tratado",
        data=to_excel_bytes(treated),
        file_name="RelatorioGeral_Tratado.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
with c2:
    st.download_button(
        "Baixar CSV tratado",
        data=to_csv_bytes(treated),
        file_name="RelatorioGeral_Tratado.csv",
        mime="text/csv",
        use_container_width=True,
    )

st.divider()
st.caption("Próximos conversores serão adicionados sem alterar a lógica já validada do RelatorioGeral.")
