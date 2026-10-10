# Network: reaching the LiveKit server from phones

The backend and LiveKit run on the same GPU machine. Phones reach both, and the screening
agent reaches LiveKit over `127.0.0.1`.

| Port | Protocol | What |
|---|---|---|
| 8000 | TCP | Backend API (`EXPO_PUBLIC_BACKEND_URL`) |
| 7880 | TCP | LiveKit signalling (`LIVEKIT_URL`) |
| 7882 | **UDP** | LiveKit media (all of it, on one port) |
| 7881 | TCP | LiveKit media fallback when UDP is blocked (slower) |

`LIVEKIT_NODE_IP` (in `docker-compose.livekit.yml`) is the address LiveKit tells phones to
send media to. It must be an address **the phones** can reach. The smoke test uses
`127.0.0.1` because its participants run on the same machine.

## Stage 1: same Wi-Fi (start here)

1. **Addresses:** set `LIVEKIT_NODE_IP` to the machine's LAN IP (`ipconfig` / `ip addr`), and
   `LIVEKIT_URL=ws://<LAN IP>:7880` for the backend.
2. **Firewall:** allow inbound TCP 8000, 7880 and 7881, and UDP 7882. On Windows, allow
   Docker Desktop and Python through Windows Defender Firewall on Private networks.
3. **Isolation:** guest or office Wi-Fi often isolates clients from each other. Use a home
   router or a phone hotspot.

## Stage 2: mobile data (the real test)

A phone on 4G/5G can't reach a LAN IP. Choose one:

### A. Port forwarding (lowest latency, self-hosted)

- **Router:** forward TCP 7880, TCP 7881 and UDP 7882 to the machine, plus TCP 8000 for the
  API (or put the API behind a tunnel).
- **Addresses:** set `LIVEKIT_NODE_IP` to the **public** IP and
  `LIVEKIT_URL=ws://<public IP>:7880`.
- **CGNAT check:** many Indian home ISPs use CGNAT. If the router's WAN IP differs from what
  `curl ifconfig.me` shows, port forwarding cannot work. Use B or C.

### B. A small cloud VM running LiveKit

Run `docker-compose.livekit.yml` on a VM with a public IP (any provider, in India for
latency). Set `LIVEKIT_NODE_IP` to the VM's IP. The backend's agent then connects to the VM
(`LIVEKIT_AGENT_URL=wss://<vm>`), which adds one internet hop for the agent only. The phones'
call stays direct to the VM.

### C. LiveKit Cloud (least setup)

Create a project at livekit.io, then:

```
LIVEKIT_URL=wss://<project>.livekit.cloud
LIVEKIT_AGENT_URL=wss://<project>.livekit.cloud
LIVEKIT_API_KEY / LIVEKIT_API_SECRET = the project's keys
```

No code changes. LiveKit Cloud runs TURN relays, so it works behind CGNAT and strict
firewalls. Trade-off: audio leaves your machine and goes through LiveKit's servers.

### Encryption

For anything beyond your own testing:

- Put the backend and LiveKit behind HTTPS/WSS (a reverse proxy with a certificate, or
  LiveKit Cloud).
- Then remove `usesCleartextTraffic` from the app.

## TURN

When both phones sit behind strict NAT, media must be relayed. LiveKit's built-in TURN needs
a domain name and a TLS certificate (see the LiveKit docs, "Deploying: TURN"). LiveKit Cloud
includes TURN. On a VM with a public IP and open UDP 7882, most mobile networks connect
without TURN.

## Latency budget

| Leg | Typical |
|---|---|
| Phone → LiveKit → phone (the call itself) | 50–150 ms on good 4G/5G in-country |
| Phone → LiveKit → agent (same machine) | same first leg; ~0 ms to the agent |
| Agent → verdict (GPU, one call) | update ~0.2 s after the audio it covers |
| First scored verdict | about 6–7 s of speech; the checks need enough speech first |
| Verdict → listener (data message) | one network leg, tens of ms |

The screening itself dominates, not the network. On the CPU it's 3–4 s per update for one
call, and it falls behind with more calls. Keep the backend on the GPU (`/api/ready` shows
`"device": "cuda"`).
