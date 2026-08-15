import json
import os
import uvicorn
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import JSONResponse, Response
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from mcp.server import Server
from mcp.server.sse import SseServerTransport
import mcp.types as types

# 1. Carrega a base de precedentes
with open("backup-precedentes.json", "r", encoding="utf-8") as f:
    PRECEDENTES = json.load(f)

# 2. Inicializa o servidor MCP padrão
app_mcp = Server("precedentes-jurisprudenciais")

@app_mcp.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="buscar_precedentes",
            description="Busca precedentes por palavra-chave na tese, tema ou ementa com filtro opcional por tribunal.",
            inputSchema={
                "type": "object",
                "properties": {
                    "termo": {"type": "string", "description": "Termo ou palavra-chave para pesquisa"},
                    "tribunal": {"type": "string", "description": "Filtro por tribunal (ex: STJ, STF, TJSC)"}
                },
                "required": ["termo"]
            }
        ),
        types.Tool(
            name="consultar_por_numero",
            description="Consulta precedente por número e tipo (Tema, Súmula, IAC, IRDR).",
            inputSchema={
                "type": "object",
                "properties": {
                    "tipo": {"type": "string", "description": "Tipo do precedente (Tema, Súmula, etc.)"},
                    "numero": {"type": "string", "description": "Número do precedente"}
                },
                "required": ["tipo", "numero"]
            }
        )
    ]

@app_mcp.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> list[types.TextContent]:
    arguments = arguments or {}
    
    if name == "buscar_precedentes":
        termo = arguments.get("termo", "").lower()
        tribunal = arguments.get("tribunal")
        resultados = []
        
        for item in PRECEDENTES:
            texto = f"{item.get('tema', '')} {item.get('tese', '')} {item.get('ementa', '')}".lower()
            trib = item.get('tribunal', '').upper()
            if termo in texto:
                if tribunal and tribunal.upper() not in trib:
                    continue
                resultados.append(item)
        
        return [types.TextContent(type="text", text=json.dumps(resultados[:10], ensure_ascii=False, indent=2))]
        
    elif name == "consultar_por_numero":
        tipo = arguments.get("tipo", "").lower()
        numero = str(arguments.get("numero", ""))
        for item in PRECEDENTES:
            if str(item.get("numero")) == numero and tipo in item.get("tipo", "").lower():
                return [types.TextContent(type="text", text=json.dumps(item, ensure_ascii=False, indent=2))]
        return [types.TextContent(type="text", text=json.dumps({"status": "não encontrado"}, ensure_ascii=False))]
        
    raise ValueError(f"Ferramenta desconhecida: {name}")

# 3. Configura o Transporte SSE
sse_transport = SseServerTransport("/messages")

async def handle_sse(request):
    async with sse_transport.connect_sse(request.scope, request.receive, request._send) as (read_stream, write_stream):
        await app_mcp.run(read_stream, write_stream, app_mcp.create_initialization_options())

async def handle_messages(request):
    await sse_transport.handle_post_message(request.scope, request.receive, request._send)

async def handle_root(request):
    return JSONResponse({
        "status": "online",
        "service": "MCP Precedentes Jurisprudenciais",
        "protocol": "Model Context Protocol",
        "sse_endpoint": "/sse"
    })

routes = [
    Route("/", endpoint=handle_root, methods=["GET"]),
    Route("/sse", endpoint=handle_sse, methods=["GET"]),
    Route("/messages", endpoint=handle_messages, methods=["POST"])
]

middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
]

app = Starlette(debug=True, routes=routes, middleware=middleware)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
