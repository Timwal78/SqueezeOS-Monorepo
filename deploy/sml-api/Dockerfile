FROM python:3.12-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --prefer-binary --no-cache-dir -r requirements.txt

COPY . .

# Run FastMCP server — SSE transport for Smithery + MCP directory clients
# REST preview API also available via sml_signal_api routes
EXPOSE 8010
CMD ["sh", "-c", "python mcp_server_sml.py"]
