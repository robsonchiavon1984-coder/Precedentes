import json
import os
import uvicorn
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.responses import JSONResponse, Response
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from mcp.server.fastmcp import FastMCP

# 1. Carrega os dados JSON
with open("backup-precedentes.json", "r", encoding="utf-8") as f:
    PRECEDENTES = json.load(f)

# 2. Inicializa o FastMCP
mcp = FastMCP("Precedentes-Jurisprudenciais")

@mcp.tool()
def buscar_precedentes(termo: str, tribunal: str = None) -> list:
    """Busca precedentes por palavra-chave na tese, tema ou ementa, com filtro opcional de tribunal (STJ, STF, TJSC, etc.)."""
    resultados = []
    termo_lower = termo.lower()
    for item in PRECEDENTES:
        texto_busca = f"{item.get('tema', '')} {item.get('tese', '')} {item.get('ementa', '')}".lower()
        tribunal_item = item.get('tribunal', '').upper()
        if termo_lower in texto_busca:
            if tribunal and tribunal.upper() not in tribunal_item:
                continue
            resultados.append(item)
    return resultados[:10]

@mcp.tool()
def consultar_por_numero(tipo: str, numero: str) -> dict:
    """Consulta precedente específico por tipo (Tema, Súmula, IAC, IRDR) e número."""
    for item in PRECEDENTES:
        if str(item.get('numero')) == str(numero) and tipo.lower() in item.get('tipo', '').lower():
            return item
    return {"status": "não encontrado"}

# 3. Rota de healthcheck raiz para validação automática de status
async def homepage(request):
    return JSONResponse({"status": "ok", "service": "mcp-precedentes", "mcp_endpoint": "/sse"})

# 4. Cria aplicação Starlette com CORS liberado (essencial para handshake do Gemini)
app = mcp.sse_app()
app.routes.insert(0, Route("/", homepage))

middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
]
app.user_middleware = middleware

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
