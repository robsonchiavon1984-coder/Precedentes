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

# 1. Carrega a base de dados
with open("backup-precedentes.json", "r", encoding="utf-8") as f:
    PRECEDENTES = json.load(f)

# Definição das ferramentas
TOOLS_SPEC = [
    {
        "name": "buscar_precedentes",
        "description": "Busca precedentes por palavra-chave na tese, tema ou ementa com filtro opcional por tribunal.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "termo": {"type": "string", "description": "Termo ou palavra-chave para pesquisa"},
                "tribunal": {"type": "string", "description": "Filtro por tribunal (ex: STJ, STF, TJSC)"}
            },
            "required": ["termo"]
        }
    },
    {
        "name": "consultar_por_numero",
        "description": "Consulta precedente por número e tipo (Tema, Súmula, IAC, IRDR).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tipo": {"type": "string", "description": "Tipo do precedente (Tema, Súmula, etc.)"},
                "numero": {"type": "string", "description": "Número do precedente"}
            },
            "required": ["tipo", "numero"]
        }
    }
]

def executar_busca(termo: str, tribunal: str = None):
    termo_lower = termo.lower()
    resultados = []
    for item in PRECEDENTES:
        texto = f"{item.get('tema', '')} {item.get('tese', '')} {item.get('ementa', '')}".lower()
        trib = item.get('tribunal', '').upper()
        if termo_lower in texto:
            if tribunal and tribunal.upper() not in trib:
                continue
            resultados.append(item)
    return resultados[:10]

def executar_consulta(tipo: str, numero: str):
    tipo_lower = tipo.lower()
    numero_str = str(numero)
    for item in PRECEDENTES:
        if str(item.get("numero")) == numero_str and tipo_lower in item.get("tipo", "").lower():
            return item
    return {"status": "não encontrado"}

# 2. Handler HTTP JSON-RPC direto (Handshake do Gemini Spark)
async def handle_jsonrpc(request):
    try:
        data = await request.json()
    except Exception:
        data = {}

    req_id = data.get("id", 1)
    method = data.get("method", "")

    if method == "initialize":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {"listChanged": False}
                },
                "serverInfo": {
                    "name": "precedentes-jurisprudenciais",
                    "version": "1.0.0"
                }
            }
        })
    elif method == "tools/list":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": TOOLS_SPEC
            }
        })
    elif method == "tools/call":
        params = data.get("params", {})
        tool_name = params.get("name")
        args = params.get("arguments", {})

        if tool_name == "buscar_precedentes":
            res = executar_busca(args.get("termo", ""), args.get("tribunal"))
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(res, ensure_ascii=False, indent=2)}]
                }
            })
        elif tool_name == "consultar_por_numero":
            res = executar_consulta(args.get("tipo", ""), args.get("numero", ""))
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(res, ensure_ascii=False, indent=2)}]
                }
            })
        else:
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Ferramenta não encontrada: {tool_name}"}
            })
    elif method == "notifications/initialized":
        return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": {}})
    else:
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"status": "ok"}
        })

# 3. Handler MCP Server via SSE oficial
app_mcp = Server("precedentes-jurisprudenciais")

@app_mcp.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name=t["name"],
            description=t["description"],
            inputSchema=t["inputSchema"]
        ) for t in TOOLS_SPEC
    ]

@app_mcp.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> list[types.TextContent]:
    args = arguments or {}
    if name == "buscar_precedentes":
        res = executar_busca(args.get("termo", ""), args.get("tribunal"))
        return [types.TextContent(type="text", text=json.dumps(res, ensure_ascii=False, indent=2))]
    elif name == "consultar_por_numero":
        res = executar_consulta(args.get("tipo", ""), args.get("numero", ""))
        return [types.TextContent(type="text", text=json.dumps(res, ensure_ascii=False, indent=2))]
    raise ValueError(f"Ferramenta desconhecida: {name}")

sse_transport = SseServerTransport("/messages")

async def handle_sse(request):
    async with sse_transport.connect_sse(request.scope, request.receive, request._send) as (read_stream, write_stream):
        await app_mcp.run(read_stream, write_stream, app_mcp.create_initialization_options())

async def handle_messages(request):
    await sse_transport.handle_post_message(request.scope, request.receive, request._send)

async def handle_root_get(request):
    return JSONResponse({
        "status": "online",
        "service": "MCP Precedentes Jurisprudenciais",
        "protocol": "Model Context Protocol",
        "sse_endpoint": "/sse"
    })

routes = [
    Route("/", endpoint=handle_root_get, methods=["GET"]),
    Route("/", endpoint=handle_jsonrpc, methods=["POST"]),
    Route("/sse", endpoint=handle_sse, methods=["GET"]),
    Route("/sse", endpoint=handle_jsonrpc, methods=["POST"]),
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
