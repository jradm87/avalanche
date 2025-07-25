#!/usr/bin/env python3
"""
telegram_utils.py
Utilitários para envio de mensagens via Telegram
"""

import requests
from config import BOT_TOKEN, CHAT_ID


def enviar_telegram(mensagem: str) -> None:
    """
    Envia uma mensagem para o chat do Telegram configurado.
    
    Args:
        mensagem: Texto da mensagem a ser enviada
    """
    if not BOT_TOKEN or not CHAT_ID:
        print(f"Telegram não configurado. Mensagem: {mensagem}")
        return
        
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": CHAT_ID,
            "text": mensagem,
            "disable_notification": False
        }
        
        response = requests.post(url, data=data, timeout=10)
        response.raise_for_status()
        
    except requests.RequestException as e:
        print(f"Erro ao enviar mensagem para Telegram: {e}")
    except Exception as e:
        print(f"Erro inesperado no Telegram: {e}")


def notificar_saldo_baixo(saldo_atual: float) -> None:
    """Notifica sobre saldo baixo."""
    enviar_telegram("💳 Saldo baixo, comprando crédito automaticamente")
    enviar_telegram(f"✅ Saldo Antigo: R$ {saldo_atual:.2f}")


def notificar_recarga_sucesso(novo_saldo: float) -> None:
    """Notifica sobre recarga bem-sucedida."""
    enviar_telegram(f"✅ Novo saldo: R$ {novo_saldo:.2f}")


def notificar_multas_pagas(novo_saldo: float) -> None:
    """Notifica sobre pagamento de multas."""
    enviar_telegram(f"✅ Multas pagas. Novo saldo: R$ {novo_saldo:.2f}")


def notificar_estacionamento_iniciado(placa: str) -> None:
    """Notifica sobre início de estacionamento."""
    enviar_telegram(f"🅿️ Estacionamento iniciado para {placa}")


def notificar_erro(erro: str) -> None:
    """Notifica sobre erros."""
    enviar_telegram(f"💥 {erro}")


def notificar_nenhum_veiculo() -> None:
    """Notifica quando nenhum veículo é encontrado."""
    enviar_telegram("❗ Nenhum veículo encontrado")