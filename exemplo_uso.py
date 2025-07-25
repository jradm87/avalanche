#!/usr/bin/env python3
"""
exemplo_uso.py
Exemplos de como usar os serviços do PareAzul Auto
"""

from pareazul_services import PareAzulService, PareAzulManualService


def exemplo_automacao_completa():
    """Exemplo de uso da automação completa."""
    print("=== Exemplo: Automação Completa ===")
    
    service = PareAzulService()
    service.executar_automacao_completa()


def exemplo_operacoes_manuais():
    """Exemplo de operações manuais específicas."""
    print("=== Exemplo: Operações Manuais ===")
    
    service = PareAzulManualService()
    
    # Consultar saldo
    saldo = service.consultar_saldo()
    print(f"Saldo atual: R$ {saldo['saldo']:.2f}")
    
    # Consultar multas para placas específicas
    placas = ["ABC1234", "XYZ5678"]  # Substitua pelas suas placas
    multas = service.consultar_multas(placas)
    print(f"Multas encontradas: {len(multas.get('resultado', []))}")
    
    # Iniciar estacionamento manual (exemplo)
    # service.iniciar_estacionamento_manual(
    #     placa="ABC1234",
    #     latitude=-24.04206,
    #     longitude=-52.37622,
    #     endereco={
    #         "rua": "Rua das Flores",
    #         "numero": "123",
    #         "bairro": "Centro"
    #     }
    # )


def exemplo_operacoes_especificas():
    """Exemplo de operações específicas."""
    print("=== Exemplo: Operações Específicas ===")
    
    service = PareAzulService()
    
    # Apenas verificar e recarregar saldo
    service.verificar_e_recarregar_saldo()
    
    # Apenas pagar multas abertas
    placas = ["ABC1234", "XYZ5678"]  # Substitua pelas suas placas
    service.pagar_multas_abertas(placas)
    
    # Apenas processar avisos de estacionamento
    veiculos = service.client.get_veiculos()
    service.processar_avisos_estacionamento(veiculos)


if __name__ == "__main__":
    # Descomente a função que deseja testar
    
    exemplo_automacao_completa()
    # exemplo_operacoes_manuais()
    # exemplo_operacoes_especificas()