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
from dataclasses import dataclass

import requests
from dotenv import load_dotenv


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURAÇÕES E CONSTANTES
# ═══════════════════════════════════════════════════════════════════════════════

load_dotenv(".envs")

# URLs e IDs
BASE_URL = os.getenv("BASE_URL")
PREFEITURA_ID = int(os.getenv("PREFEITURA_ID"))

# Credenciais
CREDENCIAL = os.getenv("CREDENCIAL")
SENHA = os.getenv("SENHA")

# Telegram
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# Arquivos
SESSION_FILE = "session.json"

# Estados das multas
ESTADOS_MULTA = ["TOLERANCIA", "ABERTA", "PAGA", "CANCELADA", "VENCIDA"]

# Localização padrão (Cascavel - PR)
DEFAULT_LATITUDE = -24.04206
DEFAULT_LONGITUDE = -52.37622

# Regras de estacionamento por tipo de veículo
REGRAS_ESTACIONAMENTO = {
    1: 85,  # carros
    2: 89,  # motos
}

# Limites financeiros
SALDO_MINIMO = 6.0
VALOR_RECARGA_PADRAO = 5.75


@dataclass
class CartaoConfig:
    """Configuração do cartão de crédito"""
    cvv: str
    numero: str
    data_expiracao: str
    bandeira: str
    titular: str
    imei: str
    uuid: str
    
    @classmethod
    def from_env(cls) -> 'CartaoConfig':
        return cls(
            cvv=os.getenv("CARTAO_CVV"),
            numero=os.getenv("CARTAO_NUMERO"),
            data_expiracao=os.getenv("CARTAO_EXPIRACAO"),
            bandeira=os.getenv("CARTAO_BANDEIRA"),
            titular=os.getenv("CARTAO_TITULAR"),
            imei=os.getenv("CARTAO_IMEI"),
            uuid=os.getenv("CARTAO_UUID")
        )


# ═══════════════════════════════════════════════════════════════════════════════
# UTILITÁRIOS
# ═══════════════════════════════════════════════════════════════════════════════

class TelegramNotifier:
    """Classe para envio de notificações via Telegram"""
    
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
    
    def send_message(self, message: str, silent: bool = False) -> None:
        """Envia mensagem via Telegram"""
        try:
            requests.post(
                f"{self.base_url}/sendMessage",
                data={
                    "chat_id": self.chat_id,
                    "text": message,
                    "disable_notification": silent
                },
                timeout=10,
            )
        except Exception as e:
            print(f"Erro ao enviar mensagem Telegram: {e}")


class TokenManager:
    """Gerenciador de tokens JWT"""
    
    def __init__(self, session_file: str):
        self.session_file = session_file
    
    def load_token(self) -> Optional[str]:
        """Carrega token válido do arquivo de sessão"""
        if not os.path.exists(self.session_file):
            return None
        
        try:
            with open(self.session_file, 'r') as f:
                data = json.load(f)
            
            if data.get("exp", 0) > time.time():
                return data["token"]
        except (json.JSONDecodeError, KeyError):
            pass
        
        return None
    
    def save_token(self, token: str) -> None:
        """Salva token no arquivo de sessão"""
        try:
            # Decodifica payload do JWT para extrair expiração
            payload = json.loads(
                base64.urlsafe_b64decode(token.split(".")[1] + "==")
            )
            
            session_data = {
                "token": token,
                "exp": payload.get("exp", 0)
            }
            
            with open(self.session_file, 'w') as f:
                json.dump(session_data, f)
        except Exception as e:
            print(f"Erro ao salvar token: {e}")


def auto_refresh_token(func):
    """Decorator para renovação automática de token em caso de 401"""
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        response = func(self, *args, **kwargs)
        
        if response.status_code == 401:
            print("Token expirado, renovando...")
            self._authenticate()
            response = func(self, *args, **kwargs)
        
        return response
    return wrapper


# ═══════════════════════════════════════════════════════════════════════════════
# CLIENTE PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════════

class PareAzulClient:
    """Cliente principal para interação com a API do PareAzul"""
    
    def __init__(self, cartao_config: CartaoConfig):
        self.session = requests.Session()
        self.cartao = cartao_config
        self.token_manager = TokenManager(SESSION_FILE)
        
        # Carrega token existente ou autentica
        self.token = self.token_manager.load_token()
        if not self.token:
            self._authenticate()
    
    def _authenticate(self) -> str:
        """Autentica na API e obtém token"""
        try:
            response = self.session.post(
                f"{BASE_URL}/v3/autenticar",
                json={"credencial": CREDENCIAL, "senha": SENHA},
                timeout=30
            )
            response.raise_for_status()
            
            self.token = response.json()["token"]
            self.token_manager.save_token(self.token)
            
            print("Autenticação realizada com sucesso")
            return self.token
        
        except requests.RequestException as e:
            raise Exception(f"Erro na autenticação: {e}")
    
    def _get_headers(self) -> Dict[str, str]:
        """Retorna cabeçalhos padrão para requisições"""
        return {
            "X-Access-Token": self.token,
            "Versao-So": "Android_v13_r33",
            "Versao-App": "PareAzul_v2025.04.11_r40134",
            "Modelo-Celular": "samsung SM-G985F",
            "Dispositivo-Uuid": self.cartao.uuid,
            "Origem-Movimento": "APP",
            "Prefeitura-Sigla": "CPM",
            "Dispositivo-Imei": self.cartao.imei,
            "Content-Type": "application/json; charset=UTF-8",
            "Accept-Encoding": "gzip, deflate, br",
            "User-Agent": "okhttp/3.12.12",
        }
    
    def _get_user_id(self) -> int:
        """Extrai ID do usuário do token JWT"""
        try:
            payload = json.loads(
                base64.urlsafe_b64decode(self.token.split(".")[1] + "==")
            )
            return payload["id"]
        except Exception as e:
            raise Exception(f"Erro ao extrair ID do usuário: {e}")
    
    # ── OPERAÇÕES FINANCEIRAS ──
    
    @auto_refresh_token
    def get_saldo(self, user_id: int) -> Dict[str, Any]:
        """Obtém saldo atual do usuário"""
        response = self.session.get(
            f"{BASE_URL}/v4/usuarios/{user_id}/saldo",
            headers=self._get_headers(),
            params={"prefeitura_id": PREFEITURA_ID},
            timeout=30
        )
        response.raise_for_status()
        return response.json()
    
    @auto_refresh_token
    def buy_credit(self, user_id: int, valor: float) -> requests.Response:
        """Compra créditos usando cartão de crédito"""
        payload = {
            "uuid_transacao": str(uuid.uuid4()),
            "cobranca": {
                "forma_pagamento": "CARTAO_CREDITO",
                "cartao": {
                    "cvv": self.cartao.cvv,
                    "numero": self.cartao.numero,
                    "salvar_cartao": True,
                    "data_expiracao": self.cartao.data_expiracao,
                    "bandeira": self.cartao.bandeira,
                    "titular": self.cartao.titular,
                },
                "valor": round(valor, 2),
                "capturar": True,
            },
            "dispositivo": {
                "imei": self.cartao.imei,
                "uuid": self.cartao.uuid
            },
            "prefeitura_id": PREFEITURA_ID,
        }
        
        response = self.session.post(
            f"{BASE_URL}/v4/usuarios/{user_id}/compras",
            headers=self._get_headers(),
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        return response
    
    # ── OPERAÇÕES DE MULTAS ──
    
    @auto_refresh_token
    def get_notificacoes(self, placas: List[str], estados: List[str] = None) -> Dict[str, Any]:
        """Obtém notificações (multas) para as placas especificadas"""
        if estados is None:
            estados = ESTADOS_MULTA
        
        params = {
            "placas": "|".join(placas),
            "estados": "|".join(estados),
            "limite": 50
        }
        
        response = self.session.get(
            f"{BASE_URL}/v4/prefeituras/{PREFEITURA_ID}/notificacoes",
            headers=self._get_headers(),
            params=params,
            timeout=30
        )
        response.raise_for_status()
        return response.json()
    
    def get_multas_abertas(self, placas: List[str]) -> List[Dict[str, Any]]:
        """Obtém apenas multas em aberto"""
        notificacoes = self.get_notificacoes(placas, ["ABERTA"])
        return [
            n for n in notificacoes.get("resultado", [])
            if n["estado"] == "ABERTA"
        ]
    
    @auto_refresh_token
    def pay_ticket(self, notification_ids: List[int]) -> Dict[str, Any]:
        """Paga multas usando saldo disponível"""
        payload = {
            "forma_pagamento": "DINHEIRO",
            "notificacoes": notification_ids
        }
        
        response = self.session.post(
            f"{BASE_URL}/v4/prefeituras/{PREFEITURA_ID}/notificacoes/pagamentos",
            headers=self._get_headers(),
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        return response.json()
    
    # ── OPERAÇÕES DE VEÍCULOS ──
    
    @auto_refresh_token
    def get_veiculos(self) -> List[Dict[str, Any]]:
        """Obtém lista de veículos do usuário"""
        response = self.session.get(
            f"{BASE_URL}/v3/usuarios/veiculos",
            headers=self._get_headers(),
            params={"dados_completos": "true"},
            timeout=30
        )
        response.raise_for_status()
        return response.json()
    
    # ── OPERAÇÕES DE ESTACIONAMENTO ──
    
    @auto_refresh_token
    def get_warnings(self) -> List[Dict[str, Any]]:
        """Obtém avisos de estacionamento"""
        response = self.session.get(
            f"{BASE_URL}/v4/prefeituras/{PREFEITURA_ID}/avisos",
            headers=self._get_headers(),
            timeout=30
        )
        response.raise_for_status()
        return response.json().get("avisos", [])
    
    @auto_refresh_token
    def start_parking(
        self,
        placa: str,
        latitude: float,
        longitude: float,
        rule_id: int,
        vehicle_type_id: int,
        street: Optional[str] = None,
        number: Optional[str] = None,
        bairro: Optional[str] = None,
        extend: bool = False,
        previous_id: int = 0,
    ) -> requests.Response:
        """Inicia estacionamento para um veículo"""
        payload = {
            "ativacao_anterior_id": previous_id,
            "uuid_ativacao": str(uuid.uuid4()),
            "cancelar": False,
            "imei_dispositivo": self.cartao.imei,
            "uuid_dispositivo": self.cartao.uuid,
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
            payload.update({
                "endereco_logradouro": street,
                "endereco_numero": number or "",
                "endereco_bairro": bairro or "",
            })
        
        response = self.session.post(
            f"{BASE_URL}/v4/prefeituras/{PREFEITURA_ID}/ativar",
            headers=self._get_headers(),
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        return response


# ═══════════════════════════════════════════════════════════════════════════════
# SERVIÇOS DE AUTOMAÇÃO
# ═══════════════════════════════════════════════════════════════════════════════

class PareAzulAutomation:
    """Serviço principal de automação do PareAzul"""
    
    def __init__(self):
        self.cartao = CartaoConfig.from_env()
        self.client = PareAzulClient(self.cartao)
        self.telegram = TelegramNotifier(BOT_TOKEN, CHAT_ID)
        self.user_id = self.client._get_user_id()
    
    def check_and_reload_balance(self) -> None:
        """Verifica saldo e recarrega se necessário"""
        try:
            saldo_info = self.client.get_saldo(self.user_id)
            saldo_atual = saldo_info["saldo"]
            
            print(f"Saldo atual: R$ {saldo_atual:.2f}")
            
            if saldo_atual < SALDO_MINIMO:
                self.telegram.send_message(
                    f"💳 Saldo baixo (R$ {saldo_atual:.2f}), recarregando automaticamente..."
                )
                
                self.client.buy_credit(self.user_id, VALOR_RECARGA_PADRAO)
                
                # Verifica novo saldo
                novo_saldo = self.client.get_saldo(self.user_id)["saldo"]
                self.telegram.send_message(
                    f"✅ Recarga realizada!\n"
                    f"Saldo anterior: R$ {saldo_atual:.2f}\n"
                    f"Novo saldo: R$ {novo_saldo:.2f}"
                )
                print(f"Recarga realizada. Novo saldo: R$ {novo_saldo:.2f}")
            else:
                print("Saldo suficiente, não é necessário recarregar")
        
        except Exception as e:
            error_msg = f"💥 Erro ao verificar/recarregar saldo: {e}"
            self.telegram.send_message(error_msg)
            print(error_msg)
    
    def pay_open_tickets(self, placas: List[str]) -> None:
        """Paga multas em aberto"""
        try:
            multas_abertas = self.client.get_multas_abertas(placas)
            
            if not multas_abertas:
                print("Nenhuma multa em aberto encontrada")
                return
            
            multa_ids = [multa["id"] for multa in multas_abertas]
            print(f"Encontradas {len(multa_ids)} multas em aberto")
            
            resultado = self.client.pay_ticket(multa_ids)
            novo_saldo = resultado.get("metadados", {}).get("saldo", 0)
            
            self.telegram.send_message(
                f"✅ {len(multa_ids)} multa(s) paga(s) automaticamente!\n"
                f"Novo saldo: R$ {novo_saldo:.2f}"
            )
            print(f"Multas pagas. Novo saldo: R$ {novo_saldo:.2f}")
        
        except Exception as e:
            error_msg = f"💥 Erro ao pagar multas: {e}"
            self.telegram.send_message(error_msg)
            print(error_msg)
    
    def process_parking_warnings(self, veiculos: List[Dict[str, Any]]) -> None:
        """Processa avisos de estacionamento e ativa automaticamente"""
        try:
            avisos = self.client.get_warnings()
            
            if not avisos:
                print("Nenhum aviso de estacionamento encontrado")
                return
            
            # Mapeia placas para tipos de veículo
            tipo_por_placa = {
                v["placa"]: v["tipo_veiculo"]["id"] 
                for v in veiculos
            }
            
            for aviso in avisos:
                placa = aviso.get("veiculo_placa") or aviso.get("placa")
                
                if not placa or placa not in tipo_por_placa:
                    print(f"Placa {placa} não encontrada nos veículos cadastrados")
                    continue
                
                tipo_veiculo_id = tipo_por_placa[placa]
                
                # Usa regra do aviso ou regra padrão por tipo
                rule_id = (
                    aviso.get("regra_valor_tempo_id") or 
                    REGRAS_ESTACIONAMENTO.get(tipo_veiculo_id)
                )
                
                if not rule_id:
                    print(f"Regra de estacionamento não encontrada para tipo {tipo_veiculo_id}")
                    continue
                
                # Ativa estacionamento
                self.client.start_parking(
                    placa=placa,
                    latitude=DEFAULT_LATITUDE,
                    longitude=DEFAULT_LONGITUDE,
                    rule_id=rule_id,
                    vehicle_type_id=tipo_veiculo_id
                )
                
                self.telegram.send_message(
                    f"🅿️ Estacionamento ativado automaticamente para {placa}"
                )
                print(f"Estacionamento ativado para {placa}")
        
        except Exception as e:
            error_msg = f"💥 Erro ao processar avisos de estacionamento: {e}"
            self.telegram.send_message(error_msg)
            print(error_msg)
    
    def run(self) -> None:
        """Executa todas as automações"""
        print("=" * 60)
        print("Iniciando PareAzul Automação...")
        print("=" * 60)
        
        try:
            # Obtém veículos cadastrados
            veiculos = self.client.get_veiculos()
            
            if not veiculos:
                self.telegram.send_message("❗ Nenhum veículo encontrado")
                print("Nenhum veículo cadastrado encontrado")
                return
            
            placas = [v["placa"] for v in veiculos]
            print(f"Veículos encontrados: {', '.join(placas)}")
            
            # Executa automações
            print("\n1. Verificando e recarregando saldo...")
            self.check_and_reload_balance()
            
            print("\n2. Verificando e pagando multas...")
            self.pay_open_tickets(placas)
            
            print("\n3. Processando avisos de estacionamento...")
            self.process_parking_warnings(veiculos)
            
            print("\n" + "=" * 60)
            print("Automação concluída com sucesso!")
            print("=" * 60)
        
        except requests.RequestException as e:
            error_msg = f"💥 Erro de conectividade: {e}"
            self.telegram.send_message(error_msg)
            print(error_msg)
        
        except Exception as e:
            error_msg = f"💥 Erro inesperado: {e}"
            self.telegram.send_message(error_msg)
            print(error_msg)


# ═══════════════════════════════════════════════════════════════════════════════
# PONTO DE ENTRADA
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    """Função principal"""
    automation = PareAzulAutomation()
    automation.run()


if __name__ == "__main__":
    main()