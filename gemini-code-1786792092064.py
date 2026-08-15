from mcp.server.fastmcp import FastMCP
import json
import os

# Inicializa o servidor FastMCP
mcp = FastMCP("Precedentes-Jurisprudenciais")

# Carrega a base de dados JSON
with open("backup-precedentes.json", "r", encoding="utf-8") as f:
    PRECEDENTES = json.load(f)

@mcp.tool()
def buscar_precedentes(termo: str, tribunal: str = None) -> list:
    """Busca precedentes por palavra-chave na tese, tema ou ementa, com filtro opcional de tribunal (STJ, STF, TJSC, etc.)."""
    resultados = []
    termo_lower = termo.lower()
    
    for item in PRECEDENTES:
        # Busca textual nas chaves comuns
        texto_busca = f"{item.get('tema', '')} {item.get('tese', '')} {item.get('ementa', '')}".lower()
        tribunal_item = item.get('tribunal', '').upper()
        
        if termo_lower in texto_busca:
            if tribunal and tribunal.upper() not in tribunal_item:
                continue
            resultados.append(item)
            
    return resultados[:10]  # Retorna os 10 mais relevantes

@mcp.tool()
def consultar_por_numero(tipo: str, numero: str) -> dict:
    """Consulta precedente específico por tipo (Tema, Súmula, IAC, IRDR) e número."""
    for item in PRECEDENTES:
        if str(item.get('numero')) == str(numero) and tipo.lower() in item.get('tipo', '').lower():
            return item
    return {"status": "não encontrado"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    mcp.run(transport="sse", host="0.0.0.0", port=port)
