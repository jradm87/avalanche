#!/usr/bin/env python3
"""
config.py
Configurações centralizadas para o PareAzul Auto
"""

import os
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv(".envs")

# URLs e IDs
BASE_URL = os.getenv("BASE_URL")
PREFEITURA_ID = int(os.getenv("PREFEITURA_ID"))

# Credenciais de login
CREDENCIAL = os.getenv("CREDENCIAL")
SENHA = os.getenv("SENHA")

# Telegram
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# Cartão de crédito
CARTAO = {
    "cvv": os.getenv("CARTAO_CVV"),
    "numero": os.getenv("CARTAO_NUMERO"),
    "data_expiracao": os.getenv("CARTAO_EXPIRACAO"),
    "bandeira": os.getenv("CARTAO_BANDEIRA"),
    "titular": os.getenv("CARTAO_TITULAR"),
    "imei": os.getenv("CARTAO_IMEI"),
    "uuid": os.getenv("CARTAO_UUID")
}

# Constantes da aplicação
SESSION_FILE = "session.json"
ESTADOS_MULTA = ["TOLERANCIA", "ABERTA", "PAGA", "CANCELADA", "VENCIDA"]
SALDO_MINIMO = 6.0
VALOR_RECARGA = 5.75

# Coordenadas padrão para estacionamento
DEFAULT_LATITUDE = -24.04206
DEFAULT_LONGITUDE = -52.37622

# Mapeamento de tipos de veículo para regras
RULE_BY_TYPE = {
    1: 85,  # carros
    2: 89,  # motos
}

# Headers da aplicação
APP_HEADERS = {
    "Versao-So": "Android_v13_r33",
    "Versao-App": "PareAzul_v2025.04.11_r40134",
    "Modelo-Celular": "samsung SM-G985F",
    "Origem-Movimento": "APP",
    "Prefeitura-Sigla": "CPM",
    "Content-Type": "application/json; charset=UTF-8",
    "Accept-Encoding": "gzip, deflate, br",
    "User-Agent": "okhttp/3.12.12",
}