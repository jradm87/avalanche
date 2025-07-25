#!/usr/bin/env python3
"""
pareazul_auto.py
Automatiza:
  • Recarga de saldo (< R$6) via cartão
  • Pagamento de multas abertas
  • Ativação de estacionamento ao chegar aviso

Requer: requests, python-dotenv
"""

from __future__ import annotations
import os
import json
import base64
import time
import uuid
from functools import wraps
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

# ─────────── Configuração ───────────
load_dotenv(".envs")

BASE_URL      = os.getenv("BASE_URL")
CREDENCIAL    = os.getenv("CREDENCIAL")
SENHA         = os.getenv("SENHA")
PREFEITURA_ID = int(os.getenv("PREFEITURA_ID"))
BOT_TOKEN     = os.getenv("BOT_TOKEN")
CHAT_ID       = os.getenv("CHAT_ID")

SESSION_FILE  = "session.json"
ESTADOS       = ["TOLERANCIA", "ABERTA", "PAGA", "CANCELADA", "VENCIDA"]

CARTAO = {
    "cvv": os.getenv("CARTAO_CVV"),
    "numero": os.getenv("CARTAO_NUMERO"),
    "data_expiracao": os.getenv("CARTAO_EXPIRACAO"),
    "bandeira": os.getenv("CARTAO_BANDEIRA"),
    "titular": os.getenv("CARTAO_TITULAR"),
    "imei": os.getenv("CARTAO_IMEI"),
    "uuid": os.getenv("CARTAO_UUID"),
}

# ─────────── Utilitários ───────────
def enviar_telegram(msg: str) -> None:
    """Envia mensagem para o Telegram."""
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": msg, "disable_notification": False},
            timeout=10,
        )
    except Exception as e:
        print("Telegram erro:", e)

def _load_token() -> Optional[str]:
    """Carrega token salvo se não expirado."""
    if not os.path.exists(SESSION_FILE):
        return None
    with open(SESSION_FILE) as f:
        data = json.load(f)
    return data["token"] if data.get("exp", 0) > time.time() else None

def _save_token(token: str) -> None:
    """Salva token e expiração."""
    payload = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))
    with open(SESSION_FILE, "w") as f:
        json.dump({"token": token, "exp": payload.get("exp", 0)}, f)

# ─────────── Decorators ───────────
def auto_refresh(func):
    @wraps(func)
    def wrapper(self, *args, **kw):
        resp = func(self, *args, **kw)
        if hasattr(resp, "status_code") and resp.status_code == 401:
            self._authenticate()
            resp = func(self, *args, **kw)
        return resp
    return wrapper

# ─────────── Cliente PareAzul ───────────
class PareAzulClient:
    def __init__(self):
        self.session = requests.Session()
        self.token = _load_token() or self._authenticate()

    def _authenticate(self) -> str:
        """Autentica e salva token."""
        r = self.session.post(
            f"{BASE_URL}/v3/autenticar",
            json={"credencial": CREDENCIAL, "senha": SENHA},
            timeout=30,
        )
        r.raise_for_status()
        self.token = r.json()["token"]
        _save_token(self.token)
        return self.token

    def _std_headers(self) -> Dict[str, str]:
        """Cabeçalhos padrão da API."""
        return {
            "X-Access-Token": self.token,
            "Versao-So": "Android_v13_r33",
            "Versao-App": "PareAzul_v2025.04.11_r40134",
            "Modelo-Celular": "samsung SM-G985F",
            "Dispositivo-Uuid": CARTAO["uuid"],
            "Origem-Movimento": "APP",
            "Prefeitura-Sigla": "CPM",
            "Dispositivo-Imei": CARTAO["imei"],
            "Content-Type": "application/json; charset=UTF-8",
            "Accept-Encoding": "gzip, deflate, br",
            "User-Agent": "okhttp/3.12.12",
        }

    # ── Finanças ──
    @auto_refresh
    def buy_credit(self, user_id: int, valor: float):
        payload = {
            "uuid_transacao": str(uuid.uuid4()),
            "cobranca": {
                "forma_pagamento": "CARTAO_CREDITO",
                "cartao": {
                    "cvv": CARTAO["cvv"],
                    "numero": CARTAO["numero"],
                    "salvar_cartao": True,
                    "data_expiracao": CARTAO["data_expiracao"],
                    "bandeira": CARTAO["bandeira"],
                    "titular": CARTAO["titular"],
                },
                "valor": round(valor, 2),
                "capturar": True,
            },
            "dispositivo": {"imei": CARTAO["imei"], "uuid": CARTAO["uuid"]},
            "prefeitura_id": PREFEITURA_ID,
        }
        r = self.session.post(
            f"{BASE_URL}/v4/usuarios/{user_id}/compras",
            headers=self._std_headers(),
            json=payload,
            timeout=30,
        )
        r.raise_for_status()
        return r

    # ── Multas ──
    @auto_refresh
    def pay_ticket(self, ids: List[int]) -> Dict[str, Any]:
        payload = {"forma_pagamento": "DINHEIRO", "notificacoes": ids}
        r = self.session.post(
            f"{BASE_URL}/v4/prefeituras/{PREFEITURA_ID}/notificacoes/pagamentos",
            headers=self._std_headers(),
            json=payload,
            timeout=30,
        )
        r.raise_for_status()
        return r.json()

    # ── Estacionamento ──
    @auto_refresh
    def start_parking(
        self,
        placa: str,
        latitude: float,
        longitude: float,
        rule_id: int,
        vehicle_type_id: int,
        *,
        street: Optional[str] = None,
        number: Optional[str] = None,
        bairro: Optional[str] = None,
        extend: bool = False,
        previous_id: int = 0,
    ):
        payload = {
            "ativacao_anterior_id": previous_id,
            "uuid_ativacao": str(uuid.uuid4()),
            "cancelar": False,
            "imei_dispositivo": CARTAO["imei"],
            "uuid_dispositivo": CARTAO["uuid"],
            "estender": extend,
            "id": 0,
            "latitude": latitude,
            "longitude": longitude,
            "prefeitura_id": PREFEITURA_ID,
            "regra_valor_tempo_id": rule_id,
            "tipo_veiculo_id": vehicle_type_id,
            "veiculo_usuario_placa": placa,
        }
        if street:
            payload.update(
                endereco_logradouro=street,
                endereco_numero=number or "",
                endereco_bairro=bairro or "",
            )
        r = self.session.post(
            f"{BASE_URL}/v4/prefeituras/{PREFEITURA_ID}/ativar",
            headers=self._std_headers(),
            json=payload,
            timeout=30,
        )
        r.raise_for_status()
        return r

    # ── Avisos ──
    def get_warnings(self) -> List[Dict[str, Any]]:
        r = self.session.get(
            f"{BASE_URL}/v4/prefeituras/{PREFEITURA_ID}/avisos",
            headers=self._std_headers(),
            timeout=30,
        )
        r.raise_for_status()
        return r.json().get("avisos", [])

    # ── Miscelânea ──
    def _get(self, path: str, **kw):
        return self.session.get(
            f"{BASE_URL}{path}", headers=self._std_headers(), timeout=30, **kw
        )

    def get_veiculos(self):
        return self._get("/v3/usuarios/veiculos", params={"dados_completos": "true"}).json()

    def get_saldo(self, user_id: int):
        return self._get(
            f"/v4/usuarios/{user_id}/saldo", params={"prefeitura_id": PREFEITURA_ID}
        ).json()

    def get_notificacoes(self, placas: List[str]):
        params = {"placas": "|".join(placas), "estados": "|".join(ESTADOS), "limite": 50}
        return self._get(
            f"/v4/prefeituras/{PREFEITURA_ID}/notificacoes", params=params
        ).json()

    def check_ticket(self, placas: List[str]):
        params = {"placas": "|".join(placas), "estados": "ABERTA"}
        return self._get(
            f"/v4/prefeituras/{PREFEITURA_ID}/notificacoes", params=params
        ).json()

# ─────────── Lógica Principal ───────────
def main():
    print("Iniciando PareAzul Auto...")
    try:
        pa = PareAzulClient()

        veiculos = pa.get_veiculos()
        if not veiculos:
            enviar_telegram("❗ Nenhum veículo encontrado")
            return

        placas = [v["placa"] for v in veiculos]
        token_payload = json.loads(base64.urlsafe_b64decode(pa.token.split(".")[1] + "=="))
        user_id = token_payload["id"]

        # ── Saldo e Recarga ──
        saldo = pa.get_saldo(user_id)
        print("Saldo atual:", saldo)
        if saldo["saldo"] < 6:
            enviar_telegram("💳 Saldo baixo, comprando crédito automaticamente")
            enviar_telegram(f"✅ Saldo Antigo: R$ {saldo['saldo']:.2f}")
            pa.buy_credit(user_id, 5.75)
            saldo = pa.get_saldo(user_id)
            enviar_telegram(f"✅ Novo saldo: R$ {saldo['saldo']:.2f}")

        # ── Multas Abertas ──
        notificacoes = pa.check_ticket(placas)
        ids = [n["id"] for n in notificacoes.get("resultado", []) if n["estado"] == "ABERTA"]
        print("Multas abertas:", ids)
        if ids:
            resp = pa.pay_ticket(ids)
            enviar_telegram(f"✅ Multas pagas. Novo saldo: R$ {resp['metadados']['saldo']:.2f}")

        # ── Avisos e Ativação de Estacionamento ──
        LAT, LON = -24.04206, -52.37622
        RULE_BY_TYPE = {1: 85, 2: 89}  # carros:1, motos:2
        tipo_by_placa = {v["placa"]: v["tipo_veiculo"]["id"] for v in veiculos}
        avisos = pa.get_warnings()
        print("Avisos recebidos:", avisos)
        for aviso in avisos:
            placa = aviso.get("veiculo_placa") or aviso.get("placa")
            tipo_id = tipo_by_placa.get(placa)
            if not tipo_id:
                continue  # desconhecido? pula
            rule_id = aviso.get("regra_valor_tempo_id") or RULE_BY_TYPE.get(tipo_id)
            pa.start_parking(placa, LAT, LON, rule_id, tipo_id)
            enviar_telegram(f"🅿️ Estacionamento iniciado para {placa}")

    except requests.RequestException as e:
        enviar_telegram(f"💥 Erro de rede: {e}")
    except Exception as e:
        enviar_telegram(f"💥 Erro inesperado: {e}")

if __name__ == "__main__":
    main()