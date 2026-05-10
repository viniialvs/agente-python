import os
import asyncio
import pandas as pd
import streamlit as st
from agents import Agent, Runner

st.set_page_config(
    page_title="Sistema Multiagente de Logística",
    page_icon="",
    layout="wide"
)

ARQUIVO_PADRAO = "Base Logistica.xlsx"


def moeda(valor):
    if pd.isna(valor):
        return "R$ 0,00"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


@st.cache_data
def carregar_base(arquivo):
    clientes = pd.read_excel(arquivo, sheet_name="dCliente")
    veiculos = pd.read_excel(arquivo, sheet_name="dVeiculo")
    fretes = pd.read_excel(arquivo, sheet_name="fFrete")
    km = pd.read_excel(arquivo, sheet_name="fKmRodado")

    clientes["ID Cliente"] = clientes["ID Cliente"].astype(str)
    veiculos["ID Veiculo"] = veiculos["ID Veiculo"].astype(str)
    fretes["ID Cliente"] = fretes["ID Cliente"].astype(str)
    fretes["ID Veiculo"] = fretes["ID Veiculo"].astype(str)
    km["ID Veiculo"] = km["ID Veiculo"].astype(str)

    fretes["Data"] = pd.to_datetime(fretes["Data"], errors="coerce")
    km["Mês"] = pd.to_datetime(km["Mês"], errors="coerce")

    fretes = fretes.merge(clientes, on="ID Cliente", how="left")
    fretes = fretes.merge(veiculos, on="ID Veiculo", how="left")

    fretes["Ano"] = fretes["Data"].dt.year
    fretes["AnoMes"] = fretes["Data"].dt.to_period("M").astype(str)

    km["Ano"] = km["Mês"].dt.year
    km["AnoMes"] = km["Mês"].dt.to_period("M").astype(str)

    km["Custo Total Frota"] = (
        km["Gasto com Combustível"].fillna(0)
        + km["Manut."].fillna(0)
        + km["Custos Fixos"].fillna(0)
    )

    km["Custo por KM"] = km["Custo Total Frota"] / km["Km percorridos"]

    fretes["Frete por KG"] = fretes["Valor do Frete Líquido"] / fretes["Peso (KG)"]
    fretes["% Frete sobre Mercadoria"] = (
        fretes["Valor do Frete Líquido"] / fretes["Valor da Mercadoria"] * 100
    )

    return clientes, veiculos, fretes, km


def aplicar_filtros(fretes, km):
    st.sidebar.header(" Filtros")

    anos = sorted(fretes["Ano"].dropna().unique().astype(int).tolist())
    anos_sel = st.sidebar.multiselect("Ano", anos, default=anos)

    ufs = sorted(fretes["UF"].dropna().unique().tolist())
    uf_sel = st.sidebar.multiselect("UF", ufs, default=ufs)

    tipos = sorted(fretes["Tipo Veículo"].dropna().unique().tolist())
    tipo_sel = st.sidebar.multiselect("Tipo de veículo", tipos, default=tipos)

    fretes_f = fretes.copy()
    fretes_f = fretes_f[fretes_f["Ano"].isin(anos_sel)]
    fretes_f = fretes_f[fretes_f["UF"].isin(uf_sel)]
    fretes_f = fretes_f[fretes_f["Tipo Veículo"].isin(tipo_sel)]

    veiculos_filtrados = fretes_f["ID Veiculo"].dropna().unique().tolist()

    km_f = km.copy()
    km_f = km_f[km_f["Ano"].isin(anos_sel)]
    km_f = km_f[km_f["ID Veiculo"].isin(veiculos_filtrados)]

    return fretes_f, km_f


def montar_contexto(fretes_f, km_f):
    total_frete = fretes_f["Valor do Frete Líquido"].sum()
    total_mercadoria = fretes_f["Valor da Mercadoria"].sum()
    total_peso = fretes_f["Peso (KG)"].sum()
    qtd_viagens = fretes_f["Viagem"].nunique()
    qtd_docs = fretes_f["Numero Documento Fiscal"].nunique()
    km_total = km_f["Km percorridos"].sum()
    custo_total = km_f["Custo Total Frota"].sum()

    frete_kg = total_frete / total_peso if total_peso else 0
    custo_km = custo_total / km_total if km_total else 0
    perc_frete = total_frete / total_mercadoria * 100 if total_mercadoria else 0

    por_uf = (
        fretes_f.groupby("UF", as_index=False)
        .agg(
            Frete=("Valor do Frete Líquido", "sum"),
            Peso=("Peso (KG)", "sum"),
            Mercadoria=("Valor da Mercadoria", "sum"),
            Viagens=("Viagem", "nunique"),
            Documentos=("Numero Documento Fiscal", "nunique"),
        )
        .sort_values("Frete", ascending=False)
        .head(10)
    )

    por_tipo = (
        fretes_f.groupby("Tipo Veículo", as_index=False)
        .agg(
            Frete=("Valor do Frete Líquido", "sum"),
            Peso=("Peso (KG)", "sum"),
            Viagens=("Viagem", "nunique"),
        )
        .sort_values("Frete", ascending=False)
    )

    por_mes = (
        fretes_f.groupby("AnoMes", as_index=False)
        .agg(
            Frete=("Valor do Frete Líquido", "sum"),
            Mercadoria=("Valor da Mercadoria", "sum"),
            Peso=("Peso (KG)", "sum"),
            Viagens=("Viagem", "nunique"),
        )
        .sort_values("AnoMes")
        .tail(12)
    )

    custos_mes = (
        km_f.groupby("AnoMes", as_index=False)
        .agg(
            Km=("Km percorridos", "sum"),
            Combustivel=("Gasto com Combustível", "sum"),
            Manutencao=("Manut.", "sum"),
            Custos_Fixos=("Custos Fixos", "sum"),
            Custo_Total=("Custo Total Frota", "sum"),
        )
        .sort_values("AnoMes")
        .tail(12)
    )

    top_veiculos = (
        km_f.groupby("ID Veiculo", as_index=False)
        .agg(
            Km=("Km percorridos", "sum"),
            Custo_Total=("Custo Total Frota", "sum"),
        )
    )
    top_veiculos["Custo por KM"] = top_veiculos["Custo_Total"] / top_veiculos["Km"]
    top_veiculos = top_veiculos.sort_values("Custo por KM", ascending=False).head(10)

    contexto = f"""
INDICADORES GERAIS
Frete líquido total: {total_frete:.2f}
Valor total da mercadoria: {total_mercadoria:.2f}
Peso total transportado KG: {total_peso:.2f}
Quantidade de viagens: {qtd_viagens}
Quantidade de documentos fiscais: {qtd_docs}
KM total rodado: {km_total:.2f}
Custo total de frota: {custo_total:.2f}
Frete por KG: {frete_kg:.4f}
Custo por KM: {custo_km:.4f}
Percentual frete sobre mercadoria: {perc_frete:.2f}%

TOP UF POR FRETE
{por_uf.to_string(index=False)}

RESUMO POR TIPO DE VEÍCULO
{por_tipo.to_string(index=False)}

RESUMO MENSAL DE FRETES
{por_mes.to_string(index=False)}

RESUMO MENSAL DE CUSTOS
{custos_mes.to_string(index=False)}

TOP VEÍCULOS POR CUSTO/KM
{top_veiculos.to_string(index=False)}
"""
    return contexto


async def executar_agentes(pergunta, contexto):
    agente_custos = Agent(
        name="Agente de Custos Logísticos",
        instructions="""
        Você é especialista em custos logísticos.
        Analise frete, combustível, manutenção, custos fixos, custo por KM e frete por KG.
        Responda com diagnóstico, riscos e recomendações práticas.
        Seja objetivo e use tópicos.
        """,
        model="gpt-4.1-mini",
    )

    agente_operacao = Agent(
        name="Agente de Operações Logísticas",
        instructions="""
        Você é especialista em operação logística.
        Analise UF, tipos de veículos, viagens, documentos, volume e concentração operacional.
        Responda com gargalos, oportunidades e prioridades operacionais.
        Seja objetivo e use tópicos.
        """,
        model="gpt-4.1-mini",
    )

    agente_riscos = Agent(
        name="Agente de Riscos e Qualidade",
        instructions="""
        Você é especialista em riscos logísticos e qualidade operacional.
        Procure riscos, dependências, concentração, custo elevado e pontos que merecem investigação.
        Não invente dados. Baseie-se apenas no contexto recebido.
        Seja objetivo e use tópicos.
        """,
        model="gpt-4.1-mini",
    )

    agente_gestor = Agent(
        name="Agente Gestor de Logística",
        instructions="""
        Você é o gestor que consolida análises de outros agentes.
        Sua resposta deve conter:
        1. resumo executivo
        2. principais achados
        3. riscos
        4. plano de ação em 5 passos
        5. decisão recomendada para a diretoria
        Use linguagem profissional e didática.
        """,
        model="gpt-4.1-mini",
    )

    entrada_base = f"""
Pergunta do usuário:
{pergunta}

Contexto dos dados:
{contexto}
"""

    resultado_custos = await Runner.run(agente_custos, entrada_base)
    resultado_operacao = await Runner.run(agente_operacao, entrada_base)
    resultado_riscos = await Runner.run(agente_riscos, entrada_base)

    consolidacao = f"""
Pergunta original:
{pergunta}

Análise do agente de custos:
{resultado_custos.final_output}

Análise do agente de operações:
{resultado_operacao.final_output}

Análise do agente de riscos:
{resultado_riscos.final_output}

Agora consolide tudo em uma resposta final para a diretoria.
"""

    resultado_final = await Runner.run(agente_gestor, consolidacao)

    return {
        "custos": resultado_custos.final_output,
        "operacao": resultado_operacao.final_output,
        "riscos": resultado_riscos.final_output,
        "gestor": resultado_final.final_output,
    }


def rodar_agentes(pergunta, contexto):
    return asyncio.run(executar_agentes(pergunta, contexto))


st.title("🤖 Sistema Multiagente de Logística")
st.caption("Projeto final: vários agentes analisam a mesma base e um agente gestor consolida a decisão.")

with st.sidebar:
    st.header(" Arquivo")
    arquivo = st.file_uploader(
        "Envie a Base Logistica.xlsx",
        type=["xlsx"],
        help="Se não enviar, o app tenta usar Base Logistica.xlsx na mesma pasta."
    )

try:
    clientes, veiculos, fretes, km = carregar_base(arquivo if arquivo else ARQUIVO_PADRAO)
except Exception as erro:
    st.error(f"Erro ao carregar a base: {erro}")
    st.stop()

fretes_f, km_f = aplicar_filtros(fretes, km)

if fretes_f.empty:
    st.warning("Nenhum dado encontrado com os filtros selecionados.")
    st.stop()

contexto = montar_contexto(fretes_f, km_f)

total_frete = fretes_f["Valor do Frete Líquido"].sum()
total_mercadoria = fretes_f["Valor da Mercadoria"].sum()
total_peso = fretes_f["Peso (KG)"].sum()
km_total = km_f["Km percorridos"].sum()
custo_total = km_f["Custo Total Frota"].sum()

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Frete Líquido", moeda(total_frete))
c2.metric("Mercadoria", moeda(total_mercadoria))
c3.metric("Peso KG", f"{total_peso:,.0f}".replace(",", "."))
c4.metric("KM Rodados", f"{km_total:,.0f}".replace(",", "."))
c5.metric("Custo Frota", moeda(custo_total))

st.subheader(" Central de Agentes")

col1, col2, col3 = st.columns(3)

pergunta = None

if col1.button("Análise executiva"):
    pergunta = "Faça uma análise executiva da operação logística e recomende ações para a diretoria."

if col2.button("Redução de custos"):
    pergunta = "Onde estão as principais oportunidades de redução de custos logísticos?"

if col3.button("Riscos operacionais"):
    pergunta = "Quais são os principais riscos e gargalos operacionais da logística?"

pergunta_digitada = st.chat_input("Pergunte algo para os agentes. Ex: Como melhorar a operação logística?")

if pergunta_digitada:
    pergunta = pergunta_digitada

if pergunta:
    if not os.getenv("OPENAI_API_KEY"):
        st.error("A variável OPENAI_API_KEY não foi encontrada. Configure a chave antes de rodar os agentes.")
        st.stop()

    with st.chat_message("user"):
        st.write(pergunta)

    with st.spinner("Agentes analisando a operação logística..."):
        respostas = rodar_agentes(pergunta, contexto)

    tabs = st.tabs([
        "Resposta Final",
        "Agente de Custos",
        "Agente de Operações",
        "Agente de Riscos",
        "Contexto usado"
    ])

    with tabs[0]:
        st.subheader(" Consolidação do Agente Gestor")
        st.write(respostas["gestor"])

    with tabs[1]:
        st.subheader(" Análise do Agente de Custos")
        st.write(respostas["custos"])

    with tabs[2]:
        st.subheader(" Análise do Agente de Operações")
        st.write(respostas["operacao"])

    with tabs[3]:
        st.subheader(" Análise do Agente de Riscos")
        st.write(respostas["riscos"])

    with tabs[4]:
        st.subheader(" Contexto enviado aos agentes")
        st.text(contexto)

else:
    st.info("Escolha uma pergunta pronta ou digite uma pergunta para iniciar os agentes.")

with st.expander("Como funciona este sistema multiagente"):
    st.markdown("""
    Este projeto usa quatro agentes:

    1. **Agente de Custos Logísticos**  
       Analisa frete, combustível, manutenção, custo por KM e frete por KG.

    2. **Agente de Operações Logísticas**  
       Analisa UF, tipo de veículo, viagens, documentos e concentração operacional.

    3. **Agente de Riscos e Qualidade**  
       Procura gargalos, riscos, concentração e pontos críticos.

    4. **Agente Gestor de Logística**  
       Consolida as análises dos outros agentes e gera uma decisão executiva.

    A diferença para um chatbot simples é que aqui existem papéis especializados.
    Cada agente tem uma responsabilidade e o agente gestor consolida o resultado final.
    """)
