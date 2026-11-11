import os
from datetime import datetime, timezone, timedelta
import requests

# ================= CONFIGURAÇÕES =================
# Lê a meta das variáveis do GitHub ou usa R$ 6.18 como padrão
PRECO_ALVO_COMERCIAL = float(os.getenv("PRECO_ALVO", "6.18"))

# Taxas estimadas para Revolut / Wise (IOF 1,1% + Spread ~0,8%)
IOF_PADRAO = 0.011
SPREAD_CONTA_GLOBAL = 0.008

# Credenciais vindas do GitHub Secrets
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
    url = "https://economia.awesomeapi.com.br/last/EUR-BRL"
    resposta = requests.get(url, timeout=10)
    resposta.raise_for_status()
    dados = resposta.json()["EURBRL"]
    
    return {
        "comercial": float(dados["bid"]),
        "maxima": float(dados["high"]),
        "minima": float(dados["low"]),
        "variacao": float(dados["pctChange"])
    }

def main():
    # Fuso horário de Brasília (UTC-3)
    fuso_br = timezone(timedelta(hours=-3))
    agora_br = datetime.now(fuso_br)
    
    info = consultar_euro()
    cotacao = info["comercial"]
    custo_efetivo = cotacao * (1 + IOF_PADRAO + SPREAD_CONTA_GLOBAL)
    
    print(f"[{agora_br.strftime('%d/%m/%Y %H:%M')}] EUR Comercial: R$ {cotacao:.4f} | VET Estimado: R$ {custo_efetivo:.4f}")

    if cotacao <= PRECO_ALVO_COMERCIAL:
        msg = (
            f"🎯 *META DO EURO ATINGIDA!*\n\n"
            f"💶 *Euro Comercial:* R$ {cotacao:.4f}\n"
            f"💳 *VET Estimado (Revolut/Wise):* R$ {custo_efetivo:.4f}\n"
            f"📉 *Mínima do dia:* R$ {info['minima']:.4f}\n"
            f"📈 *Variação:* {info['variacao']:+.2f}%\n"
            f"🕒 *Horário (BRT):* {agora_br.strftime('%H:%M')}"
        )
        enviar_telegram(msg)
        print("Alerta enviado com sucesso para o Telegram!")
    else:
        print(f"Acima da meta (R$ {PRECO_ALVO_COMERCIAL:.4f}). Nenhum alerta disparado.")

if __name__ == "__main__":
    main()
