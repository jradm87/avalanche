#!/usr/bin/env python3
"""pareazul_auto_refactored.py

Automatiza:
  • Recarga de saldo (< R$6) via cartão
  • Pagamento de multas abertas
  • Ativação de estacionamento ao chegar aviso

Requer: requests, python-dotenv
"""

from __future__ import annotations

import base64
import json
import os
import time
import uuid
from dataclasses import dataclass
from functools import wraps
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

###############################################################################
# Configuração
###############################################################################

ENV_FILE = ".envs"
load_dotenv(ENV_FILE)

# ---------------------------------------------------------------------------
# Variáveis de ambiente obrigatórias
# ---------------------------------------------------------------------------
BASE_URL: str = os.getenv("BASE_URL", "").rstrip("/")
CREDENCIAL: str = os.getenv("CREDENCIAL", "")
SENHA: str = os.getenv("SENHA", "")
PREFEITURA_ID: int = int(os.getenv("PREFEITURA_ID", "0"))
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
CHAT_ID: str = os.getenv("CHAT_ID", "")

# ---------------------------------------------------------------------------
# Validação mínima de config (fail-fast)
# ---------------------------------------------------------------------------
required_vars = {
    "BASE_URL": BASE_URL,
    "CREDENCIAL": CREDENCIAL,
    "SENHA": SENHA,
    "PREFEITURA_ID": PREFEITURA_ID,
    "BOT_TOKEN": BOT_TOKEN,
    "CHAT_ID": CHAT_ID,
}
missing = [k for k, v in required_vars.items() if not v]
if missing:
    raise RuntimeError(f"Variáveis de ambiente ausentes: {', '.join(missing)}")

###############################################################################
# Constantes & Dataclasses
###############################################################################

SESSION_FILE = "session.json"
ESTADOS = ["TOLERANCIA", "ABERTA", "PAGA", "CANCELADA", "VENCIDA"]


@dataclass(frozen=True)
class CreditCard:
    cvv: str = os.getenv("CARTAO_CVV", "")
    numero: str = os.getenv("CARTAO_NUMERO", "")
    data_expiracao: str = os.getenv("CARTAO_EXPIRACAO", "")
    bandeira: str = os.getenv("CARTAO_BANDEIRA", "")
    titular: str = os.getenv("CARTAO_TITULAR", "")
    imei: str = os.getenv("CARTAO_IMEI", "")
    uuid: str = os.getenv("CARTAO_UUID", "")

    def validate(self) -> None:
        """Verifica se todos os campos estão presentes."""
        missing_fields = [f.name for f in self.__dataclass_fields__.values() if not getattr(self, f.name)]
        if missing_fields:
            raise RuntimeError(
                f"Dados do cartão incompletos. Campos faltando: {', '.join(missing_fields)}"
            )


CARD = CreditCard()
CARD.validate()

###############################################################################
# Utilitários
###############################################################################

def _decode_jwt_payload(token: str) -> Dict[str, Any]:
    """Decodifica somente o payload do JWT (base64url)."""
    padding = "=" * (-len(token.split(".")[1]) % 4)
    return json.loads(base64.urlsafe_b64decode(token.split(".")[1] + padding))


def _load_token_from_disk() -> Optional[str]:
    if not os.path.exists(SESSION_FILE):
        return None
    with open(SESSION_FILE) as fh:
        data: Dict[str, Any] = json.load(fh)
        if data.get("exp", 0) > time.time():
            return data.get("token")
    return None


def _save_token_to_disk(token: str) -> None:
    payload = _decode_jwt_payload(token)
    with open(SESSION_FILE, "w") as fh:
        json.dump({"token": token, "exp": payload.get("exp", 0)}, fh)


###############################################################################
# Telegram
###############################################################################

def send_telegram(msg: str, disable_notification: bool = False) -> None:
    """Envia mensagem utilizando o bot do Telegram."""
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={
                "chat_id": CHAT_ID,
                "text": msg,
                "disable_notification": disable_notification,
            },
            timeout=10,
        )
    except Exception as exc:  # noqa: E722 (mantém compatibilidade ampla)
        print("Telegram erro:", exc)


###############################################################################
# Decorators
###############################################################################

def auto_refresh(func):
    """Reenvia a requisição automaticamente em caso de 401 (token expirado)."""

    @wraps(func)
    def wrapper(self: "PareAzulClient", *args, **kwargs):  # type: ignore[name-defined]
        resp = func(self, *args, **kwargs)
        if resp.status_code == 401:
            self._authenticate(force=True)
            resp = func(self, *args, **kwargs)
        return resp

    return wrapper


###############################################################################
# Cliente principal
###############################################################################

class PareAzulClient:
    def __init__(self):
        self._session = requests.Session()
        self._token: str = _load_token_from_disk() or self._authenticate()

    # ---------------------------------------------------------------------
    # Sessão / Autenticação
    # ---------------------------------------------------------------------
    def _authenticate(self, *, force: bool = False) -> str:
        if self._token and not force:
            return self._token

        response = self._session.post(
            f"{BASE_URL}/v3/autenticar",
            json={"credencial": CREDENCIAL, "senha": SENHA},
            timeout=30,
        )
        response.raise_for_status()
        self._token = response.json()["token"]
        _save_token_to_disk(self._token)
        return self._token

    # ---------------------------------------------------------------------
    # Headers
    # ---------------------------------------------------------------------
    @property
    def _headers(self) -> Dict[str, str]:
        return {
            "X-Access-Token": self._token,
            "Versao-So": "Android_v13_r33",
            "Versao-App": "PareAzul_v2025.04.11_r40134",
            "Modelo-Celular": "samsung SM-G985F",
            "Dispositivo-Uuid": CARD.uuid,
            "Origem-Movimento": "APP",
            "Prefeitura-Sigla": "CPM",
            "Dispositivo-Imei": CARD.imei,
            "Content-Type": "application/json; charset=UTF-8",
            "Accept-Encoding": "gzip, deflate, br",
            "User-Agent": "okhttp/3.12.12",
        }

    # ---------------------------------------------------------------------
    # Finanças
    # ---------------------------------------------------------------------
    @auto_refresh
    def buy_credit(self, user_id: int, valor: float):
        payload = {
            "uuid_transacao": str(uuid.uuid4()),
            "cobranca": {
                "forma_pagamento": "CARTAO_CREDITO",
                "cartao": {
                    "cvv": CARD.cvv,
                    "numero": CARD.numero,
                    "salvar_cartao": True,
                    "data_expiracao": CARD.data_expiracao,
                    "bandeira": CARD.bandeira,
                    "titular": CARD.titular,
                },
                "valor": round(valor, 2),
                "capturar": True,
            },
            "dispositivo": {"imei": CARD.imei, "uuid": CARD.uuid},
            "prefeitura_id": PREFEITURA_ID,
        }
        resp = self._session.post(
            f"{BASE_URL}/v4/usuarios/{user_id}/compras",
            headers=self._headers,
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        return resp

    # ---------------------------------------------------------------------
    # Multas
    # ---------------------------------------------------------------------
    @auto_refresh
    def pay_ticket(self, ids: List[int]) -> Dict[str, Any]:
        payload = {"forma_pagamento": "DINHEIRO", "notificacoes": ids}
        resp = self._session.post(
            f"{BASE_URL}/v4/prefeituras/{PREFEITURA_ID}/notificacoes/pagamentos",
            headers=self._headers,
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    # ---------------------------------------------------------------------
    # Estacionamento
    # ---------------------------------------------------------------------
    @auto_refresh
    def start_parking(
        self,
        placa: str,
        latitude: float,
        longitude: float,
        rule_id: int,
        vehicle_type_id: int,
        *,
        street: str | None = None,
        number: str | None = None,
        bairro: str | None = None,
        extend: bool = False,
        previous_id: int = 0,
    ):
        payload: Dict[str, Any] = {
            "ativacao_anterior_id": previous_id,
            "uuid_ativacao": str(uuid.uuid4()),
            "cancelar": False,
            "imei_dispositivo": CARD.imei,
            "uuid_dispositivo": CARD.uuid,
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
        resp = self._session.post(
            f"{BASE_URL}/v4/prefeituras/{PREFEITURA_ID}/ativar",
            headers=self._headers,
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        return resp

    # ---------------------------------------------------------------------
    # Avisos
    # ---------------------------------------------------------------------
    def get_warnings(self) -> List[Dict[str, Any]]:
        resp = self._session.get(
            f"{BASE_URL}/v4/prefeituras/{PREFEITURA_ID}/avisos",
            headers=self._headers,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("avisos", [])

    # ---------------------------------------------------------------------
    # Métodos auxiliares (GET)
    # ---------------------------------------------------------------------
    def _get(self, path: str, **kwargs):  # noqa: D401
        return self._session.get(f"{BASE_URL}{path}", headers=self._headers, timeout=30, **kwargs)

    def get_veiculos(self):
        return self._get("/v3/usuarios/veiculos", params={"dados_completos": "true"}).json()

    def get_saldo(self, user_id: int):
        return self._get(
            f"/v4/usuarios/{user_id}/saldo", params={"prefeitura_id": PREFEITURA_ID}
        ).json()

    def get_notificacoes(self, placas: List[str]):
        params = {"placas": "|".join(placas), "estados": "|".join(ESTADOS), "limite": 50}
        return self._get(f"/v4/prefeituras/{PREFEITURA_ID}/notificacoes", params=params).json()

    def check_ticket(self, placas: List[str]):
        params = {"placas": "|".join(placas), "estados": "ABERTA"}
        return self._get(f"/v4/prefeituras/{PREFEITURA_ID}/notificacoes", params=params).json()

###############################################################################
# Rotina principal
###############################################################################

def main() -> None:
    print("Iniciando PareAzul Auto...")

    try:
        pa = PareAzulClient()

        veiculos = pa.get_veiculos()
        if not veiculos:
            send_telegram("❗ Nenhum veículo encontrado")
            return

        placas = [v["placa"] for v in veiculos]
        user_id = _decode_jwt_payload(pa._token)["id"]

        # -----------------------------------------------------------------
        # Saldo / Recarga
        # -----------------------------------------------------------------
        saldo = pa.get_saldo(user_id)
        if saldo["saldo"] < 6:
            send_telegram("💳 Saldo baixo, comprando crédito automaticamente")
            send_telegram(f"✅ Saldo Antigo: R$ {saldo['saldo']:.2f}")
            pa.buy_credit(user_id, 5.75)
            saldo = pa.get_saldo(user_id)
            send_telegram(f"✅ Novo saldo: R$ {saldo['saldo']:.2f}")

        # -----------------------------------------------------------------
        # Multas abertas
        # -----------------------------------------------------------------
        ids = [n["id"] for n in pa.check_ticket(placas)["resultado"] if n["estado"] == "ABERTA"]
        if ids:
            resp = pa.pay_ticket(ids)
            send_telegram(f"✅ Multas pagas. Novo saldo: R$ {resp['metadados']['saldo']:.2f}")

        # -----------------------------------------------------------------
        # Avisos → Ativação de estacionamento
        # -----------------------------------------------------------------
        LAT, LON = -24.04206, -52.37622  # FIXME: parametrizar se necessário
        RULE_BY_TYPE = {
            1: 85,  # carros
            2: 89,  # motos
        }
        tipo_by_placa = {v["placa"]: v["tipo_veiculo"]["id"] for v in veiculos}

        for aviso in pa.get_warnings():
            placa = aviso.get("veiculo_placa") or aviso.get("placa")
            tipo_id = tipo_by_placa.get(placa)
            if not tipo_id:
                continue  # Veículo desconhecido

            rule_id = aviso.get("regra_valor_tempo_id") or RULE_BY_TYPE[tipo_id]
            pa.start_parking(placa, LAT, LON, rule_id, tipo_id)
            send_telegram(f"🅿️ Estacionamento iniciado para {placa}")

    except requests.RequestException as network_err:
        send_telegram(f"💥 Erro de rede: {network_err}")
    except Exception as exc:  # noqa: E722 (captura genérica intencional)
        send_telegram(f"💥 Erro inesperado: {exc}")


if __name__ == "__main__":
    main()