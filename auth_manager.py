#!/usr/bin/env python3
"""
auth_manager.py
Gerenciamento de autenticação e tokens JWT
"""

import os
import json
import base64
import time
from typing import Optional

from config import SESSION_FILE


def load_token() -> Optional[str]:
    """
    Carrega token salvo se ainda estiver válido.
    
    Returns:
        Token válido ou None se não existir/expirado
    """
    if not os.path.exists(SESSION_FILE):
        return None
        
    try:
        with open(SESSION_FILE, 'r') as f:
            data = json.load(f)
            
        # Verifica se o token ainda é válido
        if data.get("exp", 0) > time.time():
            return data["token"]
            
    except (json.JSONDecodeError, KeyError, FileNotFoundError):
        pass
        
    return None


def save_token(token: str) -> None:
    """
    Salva token com informações de expiração.
    
    Args:
        token: Token JWT a ser salvo
    """
    try:
        # Decodifica o payload do JWT para extrair a expiração
        payload_encoded = token.split(".")[1]
        # Adiciona padding se necessário
        payload_encoded += "=" * (4 - len(payload_encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_encoded))
        
        token_data = {
            "token": token,
            "exp": payload.get("exp", 0)
        }
        
        with open(SESSION_FILE, 'w') as f:
            json.dump(token_data, f)
            
    except (json.JSONDecodeError, IndexError, ValueError) as e:
        print(f"Erro ao salvar token: {e}")


def extract_user_id(token: str) -> Optional[int]:
    """
    Extrai o ID do usuário do token JWT.
    
    Args:
        token: Token JWT
        
    Returns:
        ID do usuário ou None se erro
    """
    try:
        payload_encoded = token.split(".")[1]
        payload_encoded += "=" * (4 - len(payload_encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_encoded))
        return payload.get("id")
    except (json.JSONDecodeError, IndexError, ValueError, KeyError):
        return None


def is_token_expired(token: str) -> bool:
    """
    Verifica se o token está expirado.
    
    Args:
        token: Token JWT
        
    Returns:
        True se expirado, False caso contrário
    """
    try:
        payload_encoded = token.split(".")[1]
        payload_encoded += "=" * (4 - len(payload_encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_encoded))
        exp = payload.get("exp", 0)
        return exp <= time.time()
    except (json.JSONDecodeError, IndexError, ValueError, KeyError):
        return True