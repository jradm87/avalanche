#!/usr/bin/env python3
"""
pareazul_client.py
Cliente principal para interação com a API do PareAzul
"""

import uuid
from functools import wraps
from typing import Any, Dict, List, Optional

import requests

from config import (
    BASE_URL, CREDENCIAL, SENHA, PREFEITURA_ID, CARTAO, 
    APP_HEADERS, ESTADOS_MULTA
)
from auth_manager import load_token, save_token


def auto_refresh(func):
    """
    Decorator para renovar automaticamente o token em caso de 401.
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        response = func(self, *args, **kwargs)
        if response.status_code == 401:
            print("Token expirado, renovando...")
            self._authenticate()
            response = func(self, *args, **kwargs)
        return response
    return wrapper


class PareAzulClient:
    """Cliente para interação com a API do PareAzul."""
    
    def __init__(self):
        self.session = requests.Session()
        self.token = load_token()
        
        if not self.token:
            self.token = self._authenticate()

    def _authenticate(self) -> str:
        """
        Autentica na API e retorna o token.
        
        Returns:
            Token de autenticação
            
        Raises:
            requests.HTTPError: Se a autenticação falhar
        """
        payload = {
            "credencial": CREDENCIAL,
            "senha": SENHA
        }
        
        response = self.session.post(
            f"{BASE_URL}/v3/autenticar",
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        
        self.token = response.json()["token"]
        save_token(self.token)
        
        print("Autenticação realizada com sucesso")
        return self.token

    def _get_headers(self) -> Dict[str, str]:
        """
        Retorna headers padrão para requisições.
        
        Returns:
            Dicionário com headers
        """
        headers = APP_HEADERS.copy()
        headers.update({
            "X-Access-Token": self.token,
            "Dispositivo-Uuid": CARTAO["uuid"],
            "Dispositivo-Imei": CARTAO["imei"],
        })
        return headers

    # ═══════════════════════════════════════════════════════════════════════════════
    # MÉTODOS DE SALDO E PAGAMENTO
    # ═══════════════════════════════════════════════════════════════════════════════

    @auto_refresh
    def get_saldo(self, user_id: int) -> Dict[str, Any]:
        """
        Obtém o saldo atual do usuário.
        
        Args:
            user_id: ID do usuário
            
        Returns:
            Dados do saldo
        """
        params = {"prefeitura_id": PREFEITURA_ID}
        response = self.session.get(
            f"{BASE_URL}/v4/usuarios/{user_id}/saldo",
            headers=self._get_headers(),
            params=params,
            timeout=30
        )
        response.raise_for_status()
        return response.json()

    @auto_refresh
    def buy_credit(self, user_id: int, valor: float) -> requests.Response:
        """
        Compra créditos usando cartão de crédito.
        
        Args:
            user_id: ID do usuário
            valor: Valor a ser carregado
            
        Returns:
            Response da requisição
        """
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
            "dispositivo": {
                "imei": CARTAO["imei"],
                "uuid": CARTAO["uuid"]
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

    # ═══════════════════════════════════════════════════════════════════════════════
    # MÉTODOS DE MULTAS
    # ═══════════════════════════════════════════════════════════════════════════════

    @auto_refresh
    def get_notificacoes(self, placas: List[str], estados: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Obtém notificações (multas) para as placas especificadas.
        
        Args:
            placas: Lista de placas dos veículos
            estados: Estados das multas a buscar (padrão: todos)
            
        Returns:
            Dados das notificações
        """
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

    @auto_refresh
    def get_multas_abertas(self, placas: List[str]) -> Dict[str, Any]:
        """
        Obtém apenas as multas em aberto para as placas especificadas.
        
        Args:
            placas: Lista de placas dos veículos
            
        Returns:
            Dados das multas abertas
        """
        return self.get_notificacoes(placas, estados=["ABERTA"])

    @auto_refresh
    def pay_ticket(self, notification_ids: List[int]) -> Dict[str, Any]:
        """
        Paga multas usando saldo da conta.
        
        Args:
            notification_ids: IDs das notificações a serem pagas
            
        Returns:
            Dados do pagamento
        """
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

    # ═══════════════════════════════════════════════════════════════════════════════
    # MÉTODOS DE ESTACIONAMENTO
    # ═══════════════════════════════════════════════════════════════════════════════

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
    ) -> requests.Response:
        """
        Inicia estacionamento para um veículo.
        
        Args:
            placa: Placa do veículo
            latitude: Latitude da localização
            longitude: Longitude da localização
            rule_id: ID da regra de estacionamento
            vehicle_type_id: ID do tipo de veículo
            street: Nome da rua (opcional)
            number: Número do endereço (opcional)
            bairro: Bairro (opcional)
            extend: Se é extensão de estacionamento
            previous_id: ID da ativação anterior (para extensões)
            
        Returns:
            Response da requisição
        """
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
        
        # Adiciona informações de endereço se fornecidas
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
    # MÉTODOS DE AVISOS E VEÍCULOS
    # ═══════════════════════════════════════════════════════════════════════════════

    @auto_refresh
    def get_warnings(self) -> List[Dict[str, Any]]:
        """
        Obtém avisos de estacionamento.
        
        Returns:
            Lista de avisos
        """
        response = self.session.get(
            f"{BASE_URL}/v4/prefeituras/{PREFEITURA_ID}/avisos",
            headers=self._get_headers(),
            timeout=30,
        )
        response.raise_for_status()
        return response.json().get("avisos", [])

    @auto_refresh
    def get_veiculos(self) -> List[Dict[str, Any]]:
        """
        Obtém lista de veículos do usuário.
        
        Returns:
            Lista de veículos
        """
        params = {"dados_completos": "true"}
        response = self.session.get(
            f"{BASE_URL}/v3/usuarios/veiculos",
            headers=self._get_headers(),
            params=params,
            timeout=30
        )
        response.raise_for_status()
        return response.json()