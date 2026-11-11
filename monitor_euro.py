import os
from datetime import datetime, timezone, timedelta
import requests

# ================= CONFIGURAÇÕES =================
PRECO_ALVO_COMERCIAL = float(os.getenv("PRECO_ALVO", "6.18"))

# Taxas estimadas para Revolut / Wise (IOF 1,1% + Spread ~0,8%)
IOF_PADRAO = 0.011
SPREAD_CONTA_GLOBAL = 0.008

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
# =================================================

def enviar_telegram(mensagem: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Aviso: Credenciais do Telegram não configuradas nos Secrets.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mensagem,
        "parse_mode": "Markdown"
    }
    resposta = requests.post(url, json=payload, timeout=10)
    resposta.raise_for_status()

def consultar_euro():
    """Consulta APIs internacionais liberadas para o GitHub Actions."""
    headers = {"User-Agent": "Mozilla/5.0"}

    # 1ª Opção: Yahoo Finance API (Tempo real do mercado financeiro global, sem bloqueio)
    try:
        url_yahoo = "https://query1.finance.yahoo.com/v8/finance/chart/EURBRL=X?interval=1m&range=1d"
        resp = requests.get(url_yahoo, headers=headers, timeout=10)
        if resp.status_code == 200:
            meta = resp.json()["chart"]["result"][0]["meta"]
            cotacao = float(meta["regularMarketPrice"])
            fechamento_anterior = float(meta.get("chartPreviousClose", cotacao))
            variacao = ((cotacao - fechamento_anterior) / fechamento_anterior) * 100
            return {
                "comercial": cotacao,
                "minima": float(meta.get("regularMarketDayLow", cotacao)),
                "variacao": variacao,
                "fonte": "Yahoo Finance (Tempo Real)"
            }
    except Exception as e:
        print(f"Aviso no Yahoo Finance: {e}. Tentando 2ª fonte...")

    # 2ª Opção: Open ExchangeRate API
    try:
        url_er = "https://open.er-api.com/v6/latest/EUR"
        resp = requests.get(url_er, headers=headers, timeout=10)
        if resp.status_code == 200:
            cotacao = float(resp.json()["rates"]["BRL"])
            return {
                "comercial": cotacao,
                "minima": cotacao,
                "variacao": 0.0,
                "fonte": "ExchangeRate-API"
            }
    except Exception as e:
        print(f"Aviso na ExchangeRate-API: {e}. Tentando 3ª fonte...")

    # 3ª Opção: Frankfurter API (Banco Central Europeu)
    url_bce = "https://api.frankfurter.app/latest?from=EUR&to=BRL"
    resp = requests.get(url_bce, headers=headers, timeout=10)
    resp.raise_for_status()
    cotacao = float(resp.json()["rates"]["BRL"])
    return {
        "comercial": cotacao,
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
    
    print(
        f"[{agora_br.strftime('%d/%m/%Y %H:%M')}] Fonte: {info['fonte']} | "
        f"EUR Comercial: R$ {cotacao:.4f} ({info['variacao']:+.2f}%) | "
        f"VET Estimado: R$ {custo_efetivo:.4f}"
    )

    if cotacao <= PRECO_ALVO_COMERCIAL:
        msg = (
            f"🎯 *META DO EURO ATINGIDA!*\n\n"
            f"💶 *Euro Comercial:* R$ {cotacao:.4f}\n"
            f"💳 *VET Estimado (Revolut/Wise):* R$ {custo_efetivo:.4f}\n"
            f"📉 *Mínima do dia:* R$ {info['minima']:.4f}\n"
            f"📈 *Variação:* {info['variacao']:+.2f}%\n"
            f"🌐 *Fonte:* {info['fonte']}\n"
            f"🕒 *Horário (BRT):* {agora_br.strftime('%H:%M')}"
        )
        enviar_telegram(msg)
        print("Alerta enviado com sucesso para o Telegram!")
    else:
        print(f"Acima da meta (R$ {PRECO_ALVO_COMERCIAL:.4f}). Nenhum alerta disparado.")

if __name__ == "__main__":
    main()
