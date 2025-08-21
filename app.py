from dotenv import load_dotenv
import streamlit as st
import pandas as pd
import numpy as np
from datetime import date
from supabase import create_client, Client
import os

# -----------------------------
# CONFIGURAÇÃO DO SUPABASE
# -----------------------------
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# -----------------------------
# CONFIGURAÇÃO DO APP
# -----------------------------
st.set_page_config(page_title="Controle de Diesel", layout="wide")
st.title("📊 Controle de Diesel – Análise por Matrizes")
st.caption("Registre lançamentos diários, calcule margem de erro (Tanque x Sistema), e gere relatórios.")

# -----------------------------
# FUNÇÕES DE BANCO DE DADOS
# -----------------------------
def salvar_lancamento(data, responsavel, sistema_lt, tanque_lt, entradas_lt, saidas_lt, diferenca, margem, obs):
    supabase.table("lancamentos_diesel").insert({
        "data": str(data),
        "responsavel": responsavel,
        "sistema_lt": float(sistema_lt),
        "tanque_lt": float(tanque_lt),
        "entradas_lt": float(entradas_lt),
        "saidas_lt": float(saidas_lt),
        "diferenca_lt": float(diferenca),
        "margem_erro_pct": float(margem),
        "obs": obs
    }).execute()

def carregar_lancamentos():
    """Carrega lançamentos do Supabase e garante datetime para 'data' e 'created_at'"""
    response = supabase.table("lancamentos_diesel").select("*").order("data").execute()
    df = pd.DataFrame(response.data)

    colunas_esperadas = ["id","data","responsavel","sistema_lt","tanque_lt","entradas_lt",
                         "saidas_lt","diferenca_lt","margem_erro_pct","obs","created_at"]
    for col in colunas_esperadas:
        if col not in df.columns:
            df[col] = pd.NA

    if not df.empty:
        df["data"] = pd.to_datetime(df["data"], errors="coerce")
        df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
        dec_cols = ["sistema_lt","tanque_lt","entradas_lt","saidas_lt","diferenca_lt","margem_erro_pct"]
        df[dec_cols] = df[dec_cols].astype(float)
    else:
        df = pd.DataFrame(columns=colunas_esperadas)

    return df

# -----------------------------
# SIDEBAR – CONFIGURAÇÕES
# -----------------------------
st.sidebar.header("Configurações")
alerta_limite = st.sidebar.number_input(
    "Limite de alerta para margem de erro (%)",
    min_value=0.0, max_value=100.0, value=5.0, step=0.1,
    help="Regra visual para destacar lançamentos fora do limite."
)

# -----------------------------
# FORMULÁRIO DE LANÇAMENTO
# -----------------------------
with st.form("lancamento_diario"):
    st.subheader("📝 Lançamento do Dia")
    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        data_input = st.date_input("Data", value=date.today())
        responsavel = st.text_input("Responsável", value="")
    with c2:
        sistema_lt = st.number_input("Quantidade no Sistema (lt)", min_value=0.0, step=0.01)
        entradas_lt = st.number_input("Entradas do dia (lt)", min_value=0.0, step=0.01)
    with c3:
        tanque_lt = st.number_input("Quantidade no Tanque (lt)", min_value=0.0, step=0.01)
        saidas_lt = st.number_input("Saídas do dia (lt)", min_value=0.0, step=0.01)
    obs = st.text_area("Observação diária", height=120)
    submitted = st.form_submit_button("Adicionar lançamento")

if submitted:
    diferenca = tanque_lt - sistema_lt
    margem = 0.0 if tanque_lt == 0 else (tanque_lt - sistema_lt) / tanque_lt * 100.0
    salvar_lancamento(
        data_input, responsavel, sistema_lt, tanque_lt,
        entradas_lt, saidas_lt, diferenca, margem, obs.strip()
    )
    st.success("✅ Lançamento salvo no Supabase!")

# -----------------------------
# CARREGA DADOS
# -----------------------------
df = carregar_lancamentos()
df_valid = df.dropna(subset=["data"])

# -----------------------------
# ABAS PRINCIPAIS
# -----------------------------
aba_hoje, aba_historico = st.tabs(["📅 Lançamento de Hoje", "📜 Dias Anteriores"])

# -----------------------------
# FUNÇÕES DE VISUALIZAÇÃO
# -----------------------------
def exibir_matriz(df_exib, alerta):
    matriz_cols = ["sistema_lt", "tanque_lt", "entradas_lt", "saidas_lt", "diferenca_lt", "margem_erro_pct"]
    if df_exib.empty:
        st.info("Nenhum dado para exibir na matriz.")
        return
    matriz = df_exib[matriz_cols].to_numpy()
    cA, cB = st.columns([1, 1])
    with cA:
        st.markdown("**Dimensão da matriz:**")
        st.write(f"{matriz.shape[0]} linhas × {matriz.shape[1]} colunas")
        st.markdown("**Ordem das colunas:** sistema, tanque, entradas, saídas, diferença, margem%")
    with cB:
        st.markdown("**Soma por coluna (Σ):**")
        soma_cols = matriz.sum(axis=0)
        soma_df = pd.DataFrame([soma_cols], columns=matriz_cols)
        st.dataframe(soma_df, use_container_width=True)
    st.dataframe(
        df_exib.assign(
            status=lambda d: np.where(np.abs(d["margem_erro_pct"]) > alerta, "⚠️ Fora do limite", "OK")
        ),
        use_container_width=True,
    )

def exibir_indicadores(df_exib):
    st.markdown("---")
    st.subheader("📌 Indicadores")
    c1, c2, c3, c4 = st.columns(4)
    if not df_exib.empty:
        with c1:
            atual = df_exib.iloc[-1]
            st.metric("Margem de erro (último)", f"{atual['margem_erro_pct']:.2f}%")
        with c2:
            media7 = df_exib.tail(7)["margem_erro_pct"].mean()
            st.metric("Média 7 últimos", f"{media7:.2f}%")
        with c3:
            max_abs = df_exib["margem_erro_pct"].abs().max()
            st.metric("Máx. desvio", f"{max_abs:.2f}%")
        with c4:
            saldo_sobra = df_exib["diferenca_lt"].sum()
            st.metric("Saldo acumulado", f"{saldo_sobra:.2f} lt")

def exibir_graficos(df_exib):
    if df_exib.empty:
        return
    st.markdown("---")
    st.subheader("📈 Tendência da Margem de Erro (%)")
    graf = df_exib[["data", "margem_erro_pct"]].set_index("data")
    st.line_chart(graf)
    st.subheader("⬆️ Entradas e ⬇️ Saídas (lt)")
    io = df_exib[["data", "entradas_lt", "saidas_lt"]].set_index("data")
    st.area_chart(io)

def exibir_relatorio(df_exib):
    if df_exib.empty:
        return
    st.markdown("---")
    st.subheader("🧾 Relatório Padrão (último lançamento)")
    ult = df_exib.iloc[-1]
    texto_relatorio = (
        f"Boa tarde, controle de Diesel: "
        f"Temos uma sobra de {ult['diferenca_lt']:.2f} lt "
        f"com uma margem de erro de {ult['margem_erro_pct']:.2f}%."
    )
    st.text_area("Texto sugerido:", value=texto_relatorio, height=140)

def exibir_exportacoes(df_exib):
    if df_exib.empty:
        return
    st.markdown("---")
    cexp1, cexp2 = st.columns([1,1])
    matriz_cols = ["sistema_lt", "tanque_lt", "entradas_lt", "saidas_lt", "diferenca_lt", "margem_erro_pct"]
    matriz_df = df_exib[matriz_cols]
    with cexp1:
        csv = df_exib.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="💾 Baixar CSV do histórico",
            data=csv,
            file_name=f"controle_diesel_{date.today().isoformat()}.csv",
            mime="text/csv",
        )
    with cexp2:
        csv_matriz = matriz_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="💾 Baixar matriz (CSV)",
            data=csv_matriz,
            file_name=f"matriz_diesel_{date.today().isoformat()}.csv",
            mime="text/csv",
        )

# -----------------------------
# ABA HOJE
# -----------------------------
with aba_hoje:
    hoje = pd.Timestamp(date.today())
    # filtrando diretamente por Timestamp
    df_hoje = df_valid[df_valid["data"].apply(lambda x: x.date() == hoje.date())]
    if not df_hoje.empty:
        exibir_matriz(df_hoje, alerta_limite)
        exibir_indicadores(df_hoje)
        exibir_graficos(df_hoje)
        exibir_relatorio(df_hoje)
        exibir_exportacoes(df_hoje)
    else:
        st.info("Nenhum lançamento para hoje. Use o formulário acima para registrar.")

# -----------------------------
# ABA DIAS ANTERIORES
# -----------------------------
with aba_historico:
    df_ant = df_valid[df_valid["data"].apply(lambda x: x.date() < hoje.date())]
    if df_ant.empty:
        st.info("Ainda não há lançamentos anteriores ao dia de hoje.")
    else:
        st.dataframe(df_ant, use_container_width=True)
        st.markdown("---")
        st.subheader("📊 Resumo Estatístico")
        st.dataframe(df_ant.describe(), use_container_width=True)
        st.markdown("---")
        st.subheader("📈 Gráficos Histórico")
        graf_ant = df_ant[["data", "margem_erro_pct"]].set_index("data")
        st.line_chart(graf_ant)
        io_ant = df_ant[["data", "entradas_lt", "saidas_lt"]].set_index("data")
        st.area_chart(io_ant)

# -----------------------------
# RODAPÉ
# -----------------------------
st.markdown("---")
st.caption(
    "Fórmula da margem de erro (%): (Tanque − Sistema) / Tanque × 100. "
    "Positivo = sobra no tanque | Negativo = sobra no sistema."
)
