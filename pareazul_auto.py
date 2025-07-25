#!/usr/bin/env python3
"""
pareazul_auto.py
Automatiza:
  • Recarga de saldo (< R$6) via cartão
  • Pagamento de multas abertas
  • Ativação de estacionamento ao chegar aviso

Requer: requests, python-dotenv
"""

import sys
import requests

from pareazul_services import PareAzulService
from telegram_utils import notificar_erro


def main():
    """Função principal que executa a automação completa."""
    print("Iniciando PareAzul Auto...")
    
    try:
        # Cria instância do serviço principal
        service = PareAzulService()
        
        # Executa automação completa
        service.executar_automacao_completa()
        
        print("PareAzul Auto finalizado com sucesso!")
        
    except requests.RequestException as e:
        error_msg = f"Erro de rede: {e}"
        print(error_msg)
        notificar_erro(error_msg)
        sys.exit(1)
        
    except Exception as e:
        error_msg = f"Erro inesperado: {e}"
        print(error_msg)
        notificar_erro(error_msg)
        sys.exit(1)


if __name__ == "__main__":
    main()