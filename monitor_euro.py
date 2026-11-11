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
    """Tenta buscar na AwesomeAPI; se tomar erro 429 do IP do GitHub, usa APIs globais de reserva."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36"
    }

    # 1ª Tentativa: AwesomeAPI (Tempo real + variação do dia)
    try:
        url = "https://economia.awesomeapi.com.br/last/EUR-BRL"
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            dados = resp.json()["EURBRL"]
            return {
                "comercial": float(dados["bid"]),
                "minima": float(dados["low"]),
                "variacao": float(dados["pctChange"]),
                "fonte": "AwesomeAPI"
            }
        print(f"Aviso: AwesomeAPI retornou status {resp.status_code}. Acionando fonte de reserva...")
    except Exception as e:
        print(f"Aviso na AwesomeAPI: {e}. Acionando fonte de reserva...")

    # 2ª Tentativa: Open ExchangeRate API (Não bloqueia IP do GitHub Actions)
    try:
        url_backup1 = "https://open.er-api.com/v6/latest/EUR"
        resp = requests.get(url_backup1, headers=headers, timeout=10)
        if resp.status_code == 200:
            cotacao = float(resp.json()["rates"]["BRL"])
            return {
                "comercial": cotacao,
                "minima": cotacao,
                "variacao": 0.0,
                "fonte": "ExchangeRate-API"
            }
    except Exception as e:
        print(f"Aviso na 2ª fonte: {e}. Acionando 3ª fonte...")

    # 3ª Tentativa: Frankfurter API (Dados do Banco Central Europeu)
    url_backup2 = "https://api.frankfurter.app/latest?from=EUR&to=BRL"
    resp = requests.get(url_backup2, headers=headers, timeout=10)
    resp.raise_for_status()
    cotacao = float(resp.json()["rates"]["BRL"])
    return {
        "comercial": cotacao,
        "minima": cotacao,
        "variacao": 0.0,
        "fonte": "Frankfurter (BCE)"
    }

def main():
    fuso_br = timezone(timedelta(hours=-3))
    agora_br = datetime.now(fuso_br)
    
    info = consultar_euro()
    cotacao = info["comercial"]
    custo_efetivo = cotacao * (1 + IOF_PADRAO + SPREAD_CONTA_GLOBAL)
    
    print(
        f"[{agora_br.strftime('%d/%m/%Y %H:%M')}] Fonte: {info['fonte']} | "
        f"EUR Comercial: R$ {cotacao:.4f} | VET Estimado: R$ {custo_efetivo:.4f}"
    )

    if cotacao <= PRECO_ALVO_COMERCIAL:
        msg = (
            f"🎯 *META DO EURO ATINGIDA!*\n\n"
            f"💶 *Euro Comercial:* R$ {cotacao:.4f}\n"
            f"💳 *VET Estimado (Revolut/Wise):* R$ {custo_efetivo:.4f}\n"
            f"📉 *Mínima registrada:* R$ {info['minima']:.4f}\n"
            f"🌐 *Fonte:* {info['fonte']}\n"
            f"🕒 *Horário (BRT):* {agora_br.strftime('%H:%M')}"
        )
        enviar_telegram(msg)
        print("Alerta enviado com sucesso para o Telegram!")
    else:
        print(f"Acima da meta (R$ {PRECO_ALVO_COMERCIAL:.4f}). Nenhum alerta disparado.")

if __name__ == "__main__":
    main()
