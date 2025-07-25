#!/usr/bin/env python3
"""
pareazul_auto.py

Automatiza:
  • Recarga de saldo (\u003c R$6) via cartão
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
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

# ────────────────────────────────────────────────────────────────────────────────
# Configurações / Constantes                                                     
# ────────────────────────────────────────────────────────────────────────────────

ENV_PATH = ".envs"      # caminho do arquivo .env com as credenciais
SESSION_FILE = "session.json"
ESTADOS_NOTIFICACAO = [
    "TOLERANCIA",
    "ABERTA",
    "PAGA",
    "CANCELADA",
    "VENCIDA",
]

SALDO_MINIMO: float = 6.0      # recarrega se saldo ficar abaixo deste valor
VALOR_RECARGA: float = 5.75    # valor padrão de recarga (R$)

# ────────────────────────────────────────────────────────────────────────────────
# Utilidades                                                                     
# ────────────────────────────────────────────────────────────────────────────────

def _b64url_decode(data: str) -> bytes:
    """Decodifica uma string base64url com padding opcional."""
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _jwt_payload(token: str) -> Dict[str, Any]:
    """Extrai e retorna o payload (segundo bloco) de um JWT."""
    return json.loads(_b64url_decode(token.split(".")[1]))


def _load_token() -> Optional[str]:
    """Retorna o token válido salvo em disco, se existir e ainda não expirado."""
    if not os.path.exists(SESSION_FILE):
        return None

    with open(SESSION_FILE) as fp:
        data = json.load(fp)

    expires = data.get("exp", 0)
    if expires and expires > time.time():
        return data.get("token")

    return None


def _save_token(token: str) -> None:
    """Persiste o token e sua data de expiração no arquivo de sessão."""
    payload = _jwt_payload(token)
    with open(SESSION_FILE, "w") as fp:
        json.dump({"token": token, "exp": payload.get("exp", 0)}, fp)


# ────────────────────────────────────────────────────────────────────────────────
# Dataclasses de Configuração                                                    
# ────────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CartaoCredito:
    cvv: str
    numero: str
    data_expiracao: str
    bandeira: str
    titular: str
    imei: str
    uuid: str


@dataclass
class Config:
    base_url: str
    credencial: str
    senha: str
    prefeitura_id: int
    bot_token: str
    chat_id: str
    cartao: CartaoCredito = field(repr=False)

    @staticmethod
    def from_env() -> "Config":
        """Carrega variáveis de ambiente usando python-dotenv."""
        load_dotenv(ENV_PATH, override=False)

        def _need(key: str) -> str:
            val = os.getenv(key)
            if not val:
                raise RuntimeError(f"Variável de ambiente obrigatória não definida: {key}")
            return val

        return Config(
            base_url=_need("BASE_URL"),
            credencial=_need("CREDENCIAL"),
            senha=_need("SENHA"),
            prefeitura_id=int(_need("PREFEITURA_ID")),
            bot_token=_need("BOT_TOKEN"),
            chat_id=_need("CHAT_ID"),
            cartao=CartaoCredito(
                cvv=_need("CARTAO_CVV"),
                numero=_need("CARTAO_NUMERO"),
                data_expiracao=_need("CARTAO_EXPIRACAO"),
                bandeira=_need("CARTAO_BANDEIRA"),
                titular=_need("CARTAO_TITULAR"),
                imei=_need("CARTAO_IMEI"),
                uuid=_need("CARTAO_UUID"),
            ),
        )


# ────────────────────────────────────────────────────────────────────────────────
# Telegram                                                                       
# ────────────────────────────────────────────────────────────────────────────────

def telegram_send(cfg: Config, msg: str) -> None:
    """Envia notificação para o BOT Telegram."""
    try:
        requests.post(
            f"https://api.telegram.org/bot{cfg.bot_token}/sendMessage",
            data={"chat_id": cfg.chat_id, "text": msg, "disable_notification": False},
            timeout=10,
        )
    except Exception as exc:
        print("[WARN] Falha ao enviar Telegram:", exc)


# ────────────────────────────────────────────────────────────────────────────────
# Decorador de atualização automática de token                                   
# ────────────────────────────────────────────────────────────────────────────────

def auto_refresh(func):
    """Reexecuta a requisição se receber HTTP 401 (token expirado)."""

    @wraps(func)
    def wrapper(self: "PareAzulClient", *args, **kwargs):  # noqa: ANN001
        resp = func(self, *args, **kwargs)
        if resp.status_code == 401:
            self._authenticate()
            resp = func(self, *args, **kwargs)
        return resp

    return wrapper


# ────────────────────────────────────────────────────────────────────────────────
# Cliente PareAzul                                                               
# ────────────────────────────────────────────────────────────────────────────────

class PareAzulClient:
    """Pequeno wrapper HTTP para a API do PareAzul."""

    def __init__(self, cfg: Config):
        self._cfg = cfg
        self.session = requests.Session()
        self.token: str = _load_token() or self._authenticate()

    # ‑- Autenticação ‑-
    def _authenticate(self) -> str:
        resp = self.session.post(
            f"{self._cfg.base_url}/v3/autenticar",
            json={"credencial": self._cfg.credencial, "senha": self._cfg.senha},
            timeout=30,
        )
        resp.raise_for_status()
        self.token = resp.json()["token"]
        _save_token(self.token)
        return self.token

    # ‑- Cabeçalhos padrão ‑-
    def _std_headers(self) -> Dict[str, str]:
        c = self._cfg.cartao
        return {
            "X-Access-Token": self.token,
            "Versao-So": "Android_v13_r33",
            "Versao-App": "PareAzul_v2025.04.11_r40134",
            "Modelo-Celular": "samsung SM-G985F",
            "Dispositivo-Uuid": c.uuid,
            "Origem-Movimento": "APP",
            "Prefeitura-Sigla": "CPM",
            "Dispositivo-Imei": c.imei,
            "Content-Type": "application/json; charset=UTF-8",
            "Accept-Encoding": "gzip, deflate, br",
            "User-Agent": "okhttp/3.12.12",
        }

    # ‑- Finanças ‑-
    @auto_refresh
    def buy_credit(self, user_id: int, valor: float):
        c = self._cfg.cartao
        payload = {
            "uuid_transacao": str(uuid.uuid4()),
            "cobranca": {
                "forma_pagamento": "CARTAO_CREDITO",
                "cartao": {
                    "cvv": c.cvv,
                    "numero": c.numero,
                    "salvar_cartao": True,
                    "data_expiracao": c.data_expiracao,
                    "bandeira": c.bandeira,
                    "titular": c.titular,
                },
                "valor": round(valor, 2),
                "capturar": True,
            },
            "dispositivo": {"imei": c.imei, "uuid": c.uuid},
            "prefeitura_id": self._cfg.prefeitura_id,
        }
        return self.session.post(
            f"{self._cfg.base_url}/v4/usuarios/{user_id}/compras",
            headers=self._std_headers(),
            json=payload,
            timeout=30,
        )

    # ‑- Multas ‑-
    @auto_refresh
    def pay_ticket(self, ids: List[int]) -> Dict[str, Any]:
        payload = {"forma_pagamento": "DINHEIRO", "notificacoes": ids}
        resp = self.session.post(
            f"{self._cfg.base_url}/v4/prefeituras/{self._cfg.prefeitura_id}/notificacoes/pagamentos",
            headers=self._std_headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    # ‑- Estacionamento ‑-
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
        c = self._cfg.cartao
        payload = {
            "ativacao_anterior_id": previous_id,
            "uuid_ativacao": str(uuid.uuid4()),
            "cancelar": False,
            "imei_dispositivo": c.imei,
            "uuid_dispositivo": c.uuid,
            "estender": extend,
            "id": 0,
            "latitude": latitude,
            "longitude": longitude,
            "prefeitura_id": self._cfg.prefeitura_id,
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
        return self.session.post(
            f"{self._cfg.base_url}/v4/prefeituras/{self._cfg.prefeitura_id}/ativar",
            headers=self._std_headers(),
            json=payload,
            timeout=30,
        )

    # ‑- Avisos ‑-
    def get_warnings(self) -> List[Dict[str, Any]]:
        resp = self.session.get(
            f"{self._cfg.base_url}/v4/prefeituras/{self._cfg.prefeitura_id}/avisos",
            headers=self._std_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("avisos", [])

    # ‑- Miscelânea / métodos auxiliares ‑-
    def _get(self, path: str, **kw):
        return self.session.get(
            f"{self._cfg.base_url}{path}", headers=self._std_headers(), timeout=30, **kw
        )

    def get_veiculos(self):
        return self._get("/v3/usuarios/veiculos", params={"dados_completos": "true"}).json()

    def get_saldo(self, user_id: int):
        return self._get(
            f"/v4/usuarios/{user_id}/saldo", params={"prefeitura_id": self._cfg.prefeitura_id}
        ).json()

    def get_notificacoes(self, placas: List[str]):
        params = {"placas": "|".join(placas), "estados": "|".join(ESTADOS_NOTIFICACAO), "limite": 50}
        return self._get(
            f"/v4/prefeituras/{self._cfg.prefeitura_id}/notificacoes", params=params
        ).json()

    def check_ticket(self, placas: List[str]):
        params = {"placas": "|".join(placas), "estados": "ABERTA"}
        return self._get(
            f"/v4/prefeituras/{self._cfg.prefeitura_id}/notificacoes", params=params
        ).json()


# ────────────────────────────────────────────────────────────────────────────────
# Funções de alto nível                                                          
# ────────────────────────────────────────────────────────────────────────────────

def handle_saldo(cfg: Config, client: PareAzulClient, user_id: int) -> None:
    saldo = client.get_saldo(user_id)
    if saldo.get("saldo", 0) < SALDO_MINIMO:
        telegram_send(cfg, "💳 Saldo baixo, comprando crédito automaticamente")
        telegram_send(cfg, f"✅ Saldo Antigo: R$ {saldo['saldo']:.2f}")
        client.buy_credit(user_id, VALOR_RECARGA)
        saldo = client.get_saldo(user_id)
        telegram_send(cfg, f"✅ Novo saldo: R$ {saldo['saldo']:.2f}")


def handle_multas(cfg: Config, client: PareAzulClient, placas: List[str]) -> None:
    ids = [n["id"] for n in client.check_ticket(placas).get("resultado", []) if n["estado"] == "ABERTA"]
    if ids:
        resp = client.pay_ticket(ids)
        novo_saldo = resp.get("metadados", {}).get("saldo", 0)
        telegram_send(cfg, f"✅ Multas pagas. Novo saldo: R$ {novo_saldo:.2f}")


def handle_avisos(cfg: Config, client: PareAzulClient, veiculos: List[Dict[str, Any]]):
    LAT, LON = -24.04206, -52.37622  # coordenadas fixas da região

    RULE_BY_TYPE = {
        1: 85,  # carros
        2: 89,  # motos
    }

    tipo_by_placa = {v["placa"]: v["tipo_veiculo"]["id"] for v in veiculos}

    for aviso in client.get_warnings():
        placa = aviso.get("veiculo_placa") or aviso.get("placa")
        if not placa:
            continue

        tipo_id = tipo_by_placa.get(placa)
        if not tipo_id:
            continue  # placa desconhecida

        rule_id = aviso.get("regra_valor_tempo_id") or RULE_BY_TYPE.get(tipo_id)
        if not rule_id:
            continue

        client.start_parking(placa, LAT, LON, rule_id, tipo_id)
        telegram_send(cfg, f"🅿️ Estacionamento iniciado para {placa}")


# ────────────────────────────────────────────────────────────────────────────────
# Main                                                                           
# ────────────────────────────────────────────────────────────────────────────────

def main() -> None:
    cfg = Config.from_env()

    telegram_send(cfg, "▶️ Iniciando PareAzul Auto…")

    try:
        pa = PareAzulClient(cfg)

        veiculos = pa.get_veiculos()
        if not veiculos:
            telegram_send(cfg, "❗ Nenhum veículo encontrado")
            return

        placas = [v["placa"] for v in veiculos]
        user_id = _jwt_payload(pa.token)["id"]

        handle_saldo(cfg, pa, user_id)
        handle_multas(cfg, pa, placas)
        handle_avisos(cfg, pa, veiculos)

    except requests.RequestException as exc:
        telegram_send(cfg, f"💥 Erro de rede: {exc}")
    except Exception as exc:  # noqa: BLE001
        telegram_send(cfg, f"💥 Erro inesperado: {exc}")


if __name__ == "__main__":
    main()