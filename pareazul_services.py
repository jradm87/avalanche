#!/usr/bin/env python3
"""
pareazul_services.py
Serviços de alto nível para automação do PareAzul
"""

from typing import Dict, List, Optional

from config import SALDO_MINIMO, VALOR_RECARGA, DEFAULT_LATITUDE, DEFAULT_LONGITUDE, RULE_BY_TYPE
from pareazul_client import PareAzulClient
from auth_manager import extract_user_id
from telegram_utils import (
    notificar_saldo_baixo, notificar_recarga_sucesso, notificar_multas_pagas,
    notificar_estacionamento_iniciado, notificar_nenhum_veiculo
)


class PareAzulService:
    """Serviço principal para automação do PareAzul."""
    
    def __init__(self):
        self.client = PareAzulClient()
        self.user_id = extract_user_id(self.client.token)
        
        if not self.user_id:
            raise ValueError("Não foi possível extrair o ID do usuário do token")

    def verificar_e_recarregar_saldo(self) -> None:
        """
        Verifica o saldo e recarrega automaticamente se estiver baixo.
        """
        print("Verificando saldo...")
        saldo_info = self.client.get_saldo(self.user_id)
        saldo_atual = saldo_info["saldo"]
        
        print(f"Saldo atual: R$ {saldo_atual:.2f}")
        
        if saldo_atual < SALDO_MINIMO:
            print(f"Saldo baixo (< R${SALDO_MINIMO:.2f}), iniciando recarga...")
            notificar_saldo_baixo(saldo_atual)
            
            # Realiza a recarga
            self.client.buy_credit(self.user_id, VALOR_RECARGA)
            
            # Verifica o novo saldo
            novo_saldo_info = self.client.get_saldo(self.user_id)
            novo_saldo = novo_saldo_info["saldo"]
            
            print(f"Recarga realizada. Novo saldo: R$ {novo_saldo:.2f}")
            notificar_recarga_sucesso(novo_saldo)
        else:
            print("Saldo adequado, não é necessário recarregar")

    def pagar_multas_abertas(self, placas: List[str]) -> None:
        """
        Verifica e paga automaticamente multas em aberto.
        
        Args:
            placas: Lista de placas dos veículos
        """
        print("Verificando multas abertas...")
        multas_response = self.client.get_multas_abertas(placas)
        multas_abertas = multas_response.get("resultado", [])
        
        # Filtra apenas multas realmente abertas
        ids_multas_abertas = [
            multa["id"] for multa in multas_abertas 
            if multa["estado"] == "ABERTA"
        ]
        
        if not ids_multas_abertas:
            print("Nenhuma multa em aberto encontrada")
            return
            
        print(f"Encontradas {len(ids_multas_abertas)} multas em aberto")
        
        # Paga as multas
        resultado_pagamento = self.client.pay_ticket(ids_multas_abertas)
        novo_saldo = resultado_pagamento["metadados"]["saldo"]
        
        print(f"Multas pagas com sucesso. Novo saldo: R$ {novo_saldo:.2f}")
        notificar_multas_pagas(novo_saldo)

    def processar_avisos_estacionamento(
        self, 
        veiculos: List[Dict], 
        latitude: Optional[float] = None,
        longitude: Optional[float] = None
    ) -> None:
        """
        Processa avisos de estacionamento e ativa automaticamente.
        
        Args:
            veiculos: Lista de veículos do usuário
            latitude: Latitude personalizada (opcional)
            longitude: Longitude personalizada (opcional)
        """
        print("Verificando avisos de estacionamento...")
        
        # Usa coordenadas padrão se não fornecidas
        lat = latitude or DEFAULT_LATITUDE
        lon = longitude or DEFAULT_LONGITUDE
        
        # Cria mapeamento de placa para tipo de veículo
        tipo_by_placa = {
            veiculo["placa"]: veiculo["tipo_veiculo"]["id"] 
            for veiculo in veiculos
        }
        
        avisos = self.client.get_warnings()
        
        if not avisos:
            print("Nenhum aviso de estacionamento encontrado")
            return
            
        print(f"Encontrados {len(avisos)} avisos")
        
        for aviso in avisos:
            placa = aviso.get("veiculo_placa") or aviso.get("placa")
            
            if not placa:
                print("Aviso sem placa identificada, pulando...")
                continue
                
            tipo_veiculo_id = tipo_by_placa.get(placa)
            
            if not tipo_veiculo_id:
                print(f"Tipo de veículo não encontrado para placa {placa}, pulando...")
                continue
            
            # Determina a regra de estacionamento
            rule_id = aviso.get("regra_valor_tempo_id") or RULE_BY_TYPE.get(tipo_veiculo_id)
            
            if not rule_id:
                print(f"Regra de estacionamento não encontrada para tipo {tipo_veiculo_id}, pulando...")
                continue
            
            try:
                print(f"Iniciando estacionamento para {placa}...")
                self.client.start_parking(
                    placa=placa,
                    latitude=lat,
                    longitude=lon,
                    rule_id=rule_id,
                    vehicle_type_id=tipo_veiculo_id
                )
                
                print(f"Estacionamento iniciado com sucesso para {placa}")
                notificar_estacionamento_iniciado(placa)
                
            except Exception as e:
                print(f"Erro ao iniciar estacionamento para {placa}: {e}")

    def executar_automacao_completa(self) -> None:
        """
        Executa o ciclo completo de automação:
        1. Verifica e recarrega saldo se necessário
        2. Paga multas abertas
        3. Processa avisos de estacionamento
        """
        print("=== Iniciando automação completa do PareAzul ===")
        
        try:
            # Obtém lista de veículos
            veiculos = self.client.get_veiculos()
            
            if not veiculos:
                print("Nenhum veículo encontrado")
                notificar_nenhum_veiculo()
                return
            
            placas = [veiculo["placa"] for veiculo in veiculos]
            print(f"Veículos encontrados: {', '.join(placas)}")
            
            # 1. Verifica e recarrega saldo
            self.verificar_e_recarregar_saldo()
            
            # 2. Paga multas abertas
            self.pagar_multas_abertas(placas)
            
            # 3. Processa avisos de estacionamento
            self.processar_avisos_estacionamento(veiculos)
            
            print("=== Automação completa finalizada ===")
            
        except Exception as e:
            print(f"Erro durante a execução da automação: {e}")
            raise


class PareAzulManualService:
    """Serviço para operações manuais específicas."""
    
    def __init__(self):
        self.client = PareAzulClient()
        self.user_id = extract_user_id(self.client.token)
        
        if not self.user_id:
            raise ValueError("Não foi possível extrair o ID do usuário do token")

    def iniciar_estacionamento_manual(
        self,
        placa: str,
        latitude: float,
        longitude: float,
        duracao_minutos: Optional[int] = None,
        endereco: Optional[Dict[str, str]] = None
    ) -> None:
        """
        Inicia estacionamento manualmente para uma placa específica.
        
        Args:
            placa: Placa do veículo
            latitude: Latitude da localização
            longitude: Longitude da localização
            duracao_minutos: Duração em minutos (opcional)
            endereco: Informações de endereço (opcional)
        """
        veiculos = self.client.get_veiculos()
        veiculo = next((v for v in veiculos if v["placa"] == placa), None)
        
        if not veiculo:
            raise ValueError(f"Veículo com placa {placa} não encontrado")
        
        tipo_veiculo_id = veiculo["tipo_veiculo"]["id"]
        rule_id = RULE_BY_TYPE.get(tipo_veiculo_id)
        
        if not rule_id:
            raise ValueError(f"Regra não encontrada para tipo de veículo {tipo_veiculo_id}")
        
        # Prepara informações de endereço se fornecidas
        street = endereco.get("rua") if endereco else None
        number = endereco.get("numero") if endereco else None
        bairro = endereco.get("bairro") if endereco else None
        
        self.client.start_parking(
            placa=placa,
            latitude=latitude,
            longitude=longitude,
            rule_id=rule_id,
            vehicle_type_id=tipo_veiculo_id,
            street=street,
            number=number,
            bairro=bairro
        )
        
        print(f"Estacionamento iniciado manualmente para {placa}")
        notificar_estacionamento_iniciado(placa)

    def consultar_saldo(self) -> Dict:
        """Consulta o saldo atual."""
        return self.client.get_saldo(self.user_id)

    def consultar_multas(self, placas: List[str]) -> Dict:
        """Consulta multas para as placas especificadas."""
        return self.client.get_notificacoes(placas)

    def recarregar_saldo(self, valor: float) -> None:
        """Recarrega saldo manualmente."""
        self.client.buy_credit(self.user_id, valor)
        print(f"Recarga de R$ {valor:.2f} realizada com sucesso")