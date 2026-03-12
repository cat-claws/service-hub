# service_hub

A lightweight local API hub using Python `http.server`.

It lets you expose many local services through one port (and one ngrok tunnel) via path prefixes.

## Files

- `hub_server.py`: reverse-proxy hub server
- `hub_config.json`: route table

## Route config format

```json
{
  "routes": [
    {
      "prefix": "/fsm",
      "target": "http://127.0.0.1:8800",
      "strip_prefix": true
    }
  ]
}
```

- `prefix`: incoming URL prefix
- `target`: local upstream base URL
- `strip_prefix`: if `true`, `/fsm/api/x` -> `/api/x` to upstream
- `target` must use a different port than the hub port (`3031`)

## Run

```bash
cd ~/service_hub
python hub_server.py --host 127.0.0.1 --port 3031 --config hub_config.json
```

Health and routes:

```bash
curl http://127.0.0.1:3031/healthz
curl http://127.0.0.1:3031/routes
```

## With ngrok

Expose only the hub port:

```bash
ngrok http 3031
```

Then call services with prefixes, e.g.:

- `https://<your-domain>.ngrok-free.dev/fsm/api/examples`
- `https://<your-domain>.ngrok-free.dev/coq/...`

## One-Command Launcher

Start hub + ngrok together on the same port:

```bash
cd ~/service_hub
./launch_hub_ngrok.sh
```

Optional port/config:

```bash
./launch_hub_ngrok.sh 3031 hub_config.json
```

Both hub and ngrok run directly from your current shell environment.

If port is already in use, either stop that process first, or let launcher stop it:

```bash
HUB_KILL_EXISTING=1 ./launch_hub_ngrok.sh
```

## Plug / unplug services

1. Edit `hub_config.json` routes.
2. No restart needed: config is reloaded on each request.

## CORS

The hub adds permissive CORS headers (`*`) and supports preflight `OPTIONS`.
