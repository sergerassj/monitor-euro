import os
import time
import socket
from datetime import datetime, timezone, timedelta
import requests
import urllib3.util.connection as urllib3_cn

# Força conexões via IPv4 para evitar congelamento (Timeout) entre GitHub Actions e Telegram
urllib3_cn.allowed_gai_family = lambda: socket.AF_INET

# ================= CONFIGURAÇÕES =================
PRECO_ALVO_COMERCIAL = float(os.getenv("PRECO_ALVO", "6.18"))

# Taxas estimadas para Revolut / Wise (IOF 1,1% + Spread ~0,8%)
IOF_PADRAO = 0.011
SPREAD_CONTA_GLOBAL = 0.008

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
# =================================================

def enviar_telegram(mensagem: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Aviso: Credenciais do Telegram não configuradas nos Secrets.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mensagem,
        "parse_mode": "HTML"
    }

    for tentativa in range(1, 4):
        try:
            resposta = requests.post(url, json=payload, timeout=30)
            if resposta.status_code != 200:
                print(f"Resposta do Telegram ({resposta.status_code}): {resposta.text}")
            resposta.raise_for_status()
            return
        except Exception as erro:
            print(f"[Tentativa {tentativa}/3] Falha ao conectar no Telegram: {erro}")
            if tentativa < 3:
                time.sleep(3)
            else:
                raise

def calcular_indicadores_tendencia(precos_fechamento: list, cotacao_atual: float):
    """Calcula Médias Móveis (7 e 20 dias) e o RSI de 14 períodos para prever direção."""
    historico = [p for p in precos_fechamento if p is not None]
    if not historico or len(historico) < 15:
        return {
            "media_7d": cotacao_atual,
            "media_20d": cotacao_atual,
            "rsi": 50.0,
            "sinal": "➖ Estável / Neutro",
            "recomendacao": "Acompanhar mercado"
        }

    # Garante que o preço atual faça parte do cálculo mais recente
    historico[-1] = cotacao_atual

    media_7d = sum(historico[-7:]) / min(len(historico), 7)
    media_20d = sum(historico[-20:]) / min(len(historico), 20)

    # Cálculo do RSI (14 dias)
    ganhos, perdas = [], []
    for i in range(1, 15):
        variacao = historico[-i] - historico[-(i + 1)]
        if variacao > 0:
            ganhos.append(variacao)
        else:
            perdas.append(abs(variacao))

    media_ganhos = sum(ganhos) / 14
    media_perdas = sum(perdas) / 14

    if media_perdas == 0:
        rsi = 100.0
    else:
        rs = media_ganhos / media_perdas
        rsi = 100.0 - (100.0 / (1.0 + rs))

    # Diagnóstico de tendência combinando Médias e RSI
    if cotacao_atual < media_7d and cotacao_atual < media_20d:
        if rsi < 38:
            sinal = "📉 Forte Baixa (Fundo de preço)"
            recomendacao = "🟢 Ótimo momento para comprar (Barato vs. mês)"
        else:
            sinal = "📉 Tendência de Baixa (Caindo)"
            recomendacao = "🟡 Pode cair mais um pouco; compre aos poucos"
    elif cotacao_atual > media_7d and cotacao_atual > media_20d:
        if rsi > 65:
            sinal = "📈 Alta Esticada (Caro)"
            recomendacao = "🔴 Evite comprar agora; chance de recuo em breve"
        else:
            sinal = "📈 Tendência de Alta (Subindo)"
            recomendacao = "🟠 Preço ganhando força de alta; atenção"
    else:
        sinal = "🔄 Lateral / Indefinido"
        recomendacao = "⚪ Oscilando próximo à média da semana"

    return {
        "media_7d": media_7d,
        "media_20d": media_20d,
        "rsi": rsi,
        "sinal": sinal,
        "recomendacao": recomendacao
    }

def consultar_euro():
    """Consulta cotação atual + histórico de 1 mês no Yahoo Finance para análise de tendência."""
    headers = {"User-Agent": "Mozilla/5.0"}

    # 1ª Opção: Yahoo Finance (1 mês de dados diários + cotação de agora)
    try:
        url_yahoo = "https://query1.finance.yahoo.com/v8/finance/chart/EURBRL=X?interval=1d&range=1mo"
        resp = requests.get(url_yahoo, headers=headers, timeout=15)
        if resp.status_code == 200:
            resultado = resp.json()["chart"]["result"][0]
            meta = resultado["meta"]
            fechamentos = resultado["indicators"]["quote"][0].get("close", [])

            cotacao = float(meta["regularMarketPrice"])
            fechamentos_validos = [p for p in fechamentos if p is not None]
            fechamento_ontem = fechamentos_validos[-2] if len(fechamentos_validos) >= 2 else float(meta.get("chartPreviousClose", cotacao))
            variacao = ((cotacao - fechamento_ontem) / fechamento_ontem) * 100

            analise = calcular_indicadores_tendencia(fechamentos_validos, cotacao)

            return {
                "comercial": cotacao,
                "maxima": float(meta.get("regularMarketDayHigh", cotacao)),
                "minima": float(meta.get("regularMarketDayLow", cotacao)),
                "variacao": variacao,
                "fonte": "Yahoo Finance",
                "analise": analise
            }
    except Exception as e:
        print(f"Aviso no Yahoo Finance: {e}. Tentando 2ª fonte...")

    # 2ª Opção de Reserva: Frankfurter API (Banco Central Europeu)
    url_bce = "https://api.frankfurter.app/latest?from=EUR&to=BRL"
    resp = requests.get(url_bce, headers=headers, timeout=15)
    resp.raise_for_status()
    cotacao = float(resp.json()["rates"]["BRL"])
    analise = calcular_indicadores_tendencia([], cotacao)
    return {
        "comercial": cotacao,
        "maxima": cotacao,
        "minima": cotacao,
        "variacao": 0.0,
        "fonte": "Banco Central Europeu",
        "analise": analise
    }

def main():
    fuso_br = timezone(timedelta(hours=-3))
    agora_br = datetime.now(fuso_br)
    
    info = consultar_euro()
    cotacao = info["comercial"]
    analise = info["analise"]
    custo_efetivo = cotacao * (1 + IOF_PADRAO + SPREAD_CONTA_GLOBAL)
    
    eh_horario_fechamento = (agora_br.hour == 18 and agora_br.minute < 15)
    
    print(
        f"[{agora_br.strftime('%d/%m/%Y %H:%M')}] EUR: R$ {cotacao:.4f} ({info['variacao']:+.2f}%) | "
        f"Média 7d: R$ {analise['media_7d']:.4f} | RSI: {analise['rsi']:.0f} | {analise['sinal']}"
    )

    # 1. Alerta quando atinge a meta
    if cotacao <= PRECO_ALVO_COMERCIAL:
        msg = (
            f"🎯 <b>META DO EURO ATINGIDA!</b>\n\n"
            f"💶 <b>Euro Comercial:</b> R$ {cotacao:.4f} ({info['variacao']:+.2f}%)\n"
            f"💳 <b>VET Estimado (Revolut/Wise):</b> R$ {custo_efetivo:.4f}\n"
            f"📉 <b>Mínima / Máxima hoje:</b> R$ {info['minima']:.4f} / R$ {info['maxima']:.4f}\n\n"
            f"🧭 <b>Termômetro de Tendência:</b>\n"
            f"• <b>Direção:</b> {analise['sinal']}\n"
            f"• <b>Média 7 dias:</b> R$ {analise['media_7d']:.4f}\n"
            f"• <b>Média 20 dias:</b> R$ {analise['media_20d']:.4f}\n"
            f"• <b>Força (RSI):</b> {analise['rsi']:.0f}/100\n"
            f"💡 <b>Leitura:</b> {analise['recomendacao']}\n\n"
            f"🕒 <b>Horário (BRT):</b> {agora_br.strftime('%H:%M')}"
        )
        enviar_telegram(msg)
        print("Alerta com análise de tendência enviado para o Telegram!")

    # 2. Boletim Diário das 18h
    elif eh_horario_fechamento:
        diferenca = cotacao - PRECO_ALVO_COMERCIAL
        msg = (
            f"📊 <b>FECHAMENTO DO DIA — EURO (18h)</b>\n\n"
            f"💶 <b>Fechamento Comercial:</b> R$ {cotacao:.4f} ({info['variacao']:+.2f}%)\n"
            f"💳 <b>VET Estimado (Revolut/Wise):</b> R$ {custo_efetivo:.4f}\n"
            f"📉 <b>Mínima / Máxima hoje:</b> R$ {info['minima']:.4f} / R$ {info['maxima']:.4f}\n\n"
            f"🧭 <b>Previsão & Tendência:</b>\n"
            f"• <b>Direção:</b> {analise['sinal']}\n"
            f"• <b>Média 7 dias:</b> R$ {analise['media_7d']:.4f}\n"
            f"• <b>Média 20 dias:</b> R$ {analise['media_20d']:.4f}\n"
            f"• <b>Força (RSI):</b> {analise['rsi']:.0f}/100\n"
            f"💡 <b>Leitura:</b> {analise['recomendacao']}\n\n"
            f"🎯 <b>Sua Meta:</b> R$ {PRECO_ALVO_COMERCIAL:.4f} <i>(Faltam R$ {diferenca:.4f})</i>"
        )
        enviar_telegram(msg)
        print("Resumo diário das 18h com previsão enviado para o Telegram!")

    else:
        print(f"Acima da meta (R$ {PRECO_ALVO_COMERCIAL:.4f}) e fora do horário de fechamento.")

if __name__ == "__main__":
    main()
