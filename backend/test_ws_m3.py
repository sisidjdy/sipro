"""EPIC M3 WebSocket smoke test: connect, heartbeat, instant push, mark_all_read.

Tests against a base WS URL. Usage:
    python test_ws_m3.py                # ws://localhost:8001
    python test_ws_m3.py wss://host     # public ingress
"""
import asyncio
import json
import sys

import requests
import websockets

HTTP = "http://localhost:8001/api"
WS_BASE = sys.argv[1] if len(sys.argv) > 1 else "ws://localhost:8001"
WS = f"{WS_BASE}/api/ws/notifications"
PW = "Sipro#2026"
EMAIL = "owner@sipro.co.id"


def login():
    r = requests.post(f"{HTTP}/auth/login", json={"email": EMAIL, "password": PW}, timeout=10)
    r.raise_for_status()
    return r.json()["access_token"]


async def recv(ws, timeout=8):
    return json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))


async def main():
    token = login()
    results = []

    def check(name, cond, detail=""):
        results.append((name, cond, detail))
        print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

    url = f"{WS}?token={token}"
    print(f"Connecting: {WS_BASE}...")
    async with websockets.connect(url, open_timeout=10) as ws:
        hello = await recv(ws)
        check("hello event on connect", hello.get("event") == "hello", str(hello))
        check("hello reports transport=websocket", hello.get("transport") == "websocket")
        check("hello has unread int", isinstance(hello.get("unread"), int))

        # heartbeat
        await ws.send(json.dumps({"action": "ping"}))
        pong = await recv(ws)
        check("ping -> pong", pong.get("event") == "pong", str(pong))

        # instant push: trigger a notification (self @mention) via HTTP while connected
        h = {"Authorization": f"Bearer {token}"}
        requests.post(f"{HTTP}/activities", headers=h, json={
            "entity_type": "lead", "entity_id": "m3-ws-test",
            "body": "Uji push realtime M3 @owner", "type": "comment",
            "mentions": [EMAIL],
        }, timeout=10).raise_for_status()

        got_push = False
        for _ in range(3):
            msg = await recv(ws, timeout=8)
            if msg.get("event") == "notification":
                got_push = True
                check("instant notification push received", True,
                      f"title={msg.get('data', {}).get('title')} unread={msg.get('unread')}")
                check("push includes unread count", isinstance(msg.get("unread"), int))
                break
        if not got_push:
            check("instant notification push received", False, "no notification event within timeout")

        # mark_all_read round-trip
        await ws.send(json.dumps({"action": "mark_all_read"}))
        for _ in range(3):
            msg = await recv(ws, timeout=8)
            if msg.get("event") == "unread":
                check("mark_all_read -> unread=0", msg.get("unread") == 0, str(msg))
                break

    passed = sum(1 for _, c, _ in results if c)
    print("-" * 55)
    print(f"RESULT: {passed}/{len(results)} checks passed")
    if passed != len(results):
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
