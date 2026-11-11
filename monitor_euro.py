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

    # Faz até 3 tentativas caso a rede oscile
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

def consultar_euro():
    """Consulta APIs internacionais liberadas para o GitHub Actions."""
    headers = {"User-Agent": "Mozilla/5.0"}

    # 1ª Opção: Yahoo Finance API (Tempo real com Máxima, Mínima e Variação)
    try:
        url_yahoo = "https://query1.finance.yahoo.com/v8/finance/chart/EURBRL=X?interval=1m&range=1d"
        resp = requests.get(url_yahoo, headers=headers, timeout=15)
        if resp.status_code == 200:
            meta = resp.json()["chart"]["result"][0]["meta"]
            cotacao = float(meta["regularMarketPrice"])
            fechamento_anterior = float(meta.get("chartPreviousClose", cotacao))
            variacao = ((cotacao - fechamento_anterior) / fechamento_anterior) * 100
            return {
                "comercial": cotacao,
                "maxima": float(meta.get("regularMarketDayHigh", cotacao)),
                "minima": float(meta.get("regularMarketDayLow", cotacao)),
                "variacao": variacao,
                "fonte": "Yahoo Finance (Tempo Real)"
            }
    except Exception as e:
        print(f"Aviso no Yahoo Finance: {e}. Tentando 2ª fonte...")

    # 2ª Opção: Open ExchangeRate API
    try:
        url_er = "https://open.er-api.com/v6/latest/EUR"
        resp = requests.get(url_er, headers=headers, timeout=15)
        if resp.status_code == 200:
            cotacao = float(resp.json()["rates"]["BRL"])
            return {
                "comercial": cotacao,
                "maxima": cotacao,
                "minima": cotacao,
                "variacao": 0.0,
                "fonte": "ExchangeRate-API"
            }
    except Exception as e:
        print(f"Aviso na ExchangeRate-API: {e}. Tentando 3ª fonte...")

    # 3ª Opção: Frankfurter API (Banco Central Europeu)
    url_bce = "https://api.frankfurter.app/latest?from=EUR&to=BRL"
    resp = requests.get(url_bce, headers=headers, timeout=15)
    resp.raise_for_status()
    cotacao = float(resp.json()["rates"]["BRL"])
    return {
        "comercial": cotacao,
        "maxima": cotacao,
        "minima": cotacao,
        "variacao": 0.0,
        "fonte": "Banco Central Europeu"
    }

def main():
    fuso_br = timezone(timedelta(hours=-3))
    agora_br = datetime.now(fuso_br)
    
    info = consultar_euro()
    cotacao = info["comercial"]
    custo_efetivo = cotacao * (1 + IOF_PADRAO + SPREAD_CONTA_GLOBAL)
    
    # Verifica se está na janela das 18h00 às 18h14 (Horário de Brasília)
    eh_horario_fechamento = (agora_br.hour == 18 and agora_br.minute < 15)
    
    print(
        f"[{agora_br.strftime('%d/%m/%Y %H:%M')}] Fonte: {info['fonte']} | "
        f"EUR Comercial: R$ {cotacao:.4f} ({info['variacao']:+.2f}%) | "
        f"VET Estimado: R$ {custo_efetivo:.4f}"
    )

    # 1. Prioridade: Alerta se o Euro atingiu ou caiu abaixo da sua meta
    if cotacao <= PRECO_ALVO_COMERCIAL:
        msg = (
            f"🎯 <b>META DO EURO ATINGIDA!</b>\n\n"
            f"💶 <b>Euro Comercial:</b> R$ {cotacao:.4f}\n"
            f"💳 <b>VET Estimado (Revolut/Wise):</b> R$ {custo_efetivo:.4f}\n"
            f"📉 <b>Mínima do dia:</b> R$ {info['minima']:.4f}\n"
            f"📈 <b>Máxima do dia:</b> R$ {info['maxima']:.4f}\n"
            f"📊 <b>Variação:</b> {info['variacao']:+.2f}%\n"
            f"🌐 <b>Fonte:</b> {info['fonte']}\n"
            f"🕒 <b>Horário (BRT):</b> {agora_br.strftime('%H:%M')}"
        )
        enviar_telegram(msg)
        print("Alerta de meta atingida enviado com sucesso para o Telegram!")

    # 2. Boletim Diário das 18h (Mesmo se não bater a meta)
    elif eh_horario_fechamento:
        diferenca = cotacao - PRECO_ALVO_COMERCIAL
        msg = (
            f"📊 <b>FECHAMENTO DO DIA — EURO (18h)</b>\n\n"
            f"💶 <b>Fechamento Comercial:</b> R$ {cotacao:.4f}\n"
            f"💳 <b>VET Estimado (Revolut/Wise):</b> R$ {custo_efetivo:.4f}\n"
            f"📉 <b>Mínima de hoje:</b> R$ {info['minima']:.4f}\n"
            f"📈 <b>Máxima de hoje:</b> R$ {info['maxima']:.4f}\n"
            f"🔄 <b>Variação no dia:</b> {info['variacao']:+.2f}%\n\n"
            f"🎯 <b>Sua Meta:</b> R$ {PRECO_ALVO_COMERCIAL:.4f} <i>(Faltam R$ {diferenca:.4f})</i>\n"
            f"🌐 <b>Fonte:</b> {info['fonte']}"
        )
        enviar_telegram(msg)
        print("Resumo diário das 18h enviado com sucesso para o Telegram!")

    else:
        print(f"Acima da meta (R$ {PRECO_ALVO_COMERCIAL:.4f}) e fora do horário de fechamento. Nenhum alerta disparado.")

if __name__ == "__main__":
    main()
