"""Comprehensive backend test for EPIC M3 WebSocket notifications + regression tests.

Tests:
1. WebSocket /api/ws/notifications with valid token
2. WebSocket with invalid token (should close 4401)
3. Heartbeat ping→pong
4. Instant push notification
5. mark_all_read action
6. mark_read individual notification
7. SSE fallback /api/notifications/stream
8. Regression: login, /api/work/home, /api/notifications, RBAC
"""
import asyncio
import json
import sys
import time

import requests
import websockets

# Configuration
BASE_URL = "http://localhost:8001"
API_URL = f"{BASE_URL}/api"
WS_URL = "ws://localhost:8001/api/ws/notifications"
PASSWORD = "Sipro#2026"

# Test users
OWNER_EMAIL = "owner@sipro.co.id"
SALES_EMAIL = "sales@sipro.co.id"
FINANCE_EMAIL = "finance@sipro.co.id"


class TestRunner:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.results = []

    def check(self, name, condition, detail=""):
        """Record a test result."""
        self.tests_run += 1
        if condition:
            self.tests_passed += 1
        status = "✅ PASS" if condition else "❌ FAIL"
        msg = f"{status} | {name}"
        if detail:
            msg += f" — {detail}"
        print(msg)
        self.results.append({"name": name, "passed": condition, "detail": detail})
        return condition

    def print_summary(self):
        """Print test summary."""
        print("\n" + "=" * 70)
        print(f"TEST SUMMARY: {self.tests_passed}/{self.tests_run} tests passed")
        print("=" * 70)
        if self.tests_passed < self.tests_run:
            print("\nFailed tests:")
            for r in self.results:
                if not r["passed"]:
                    print(f"  ❌ {r['name']}")
                    if r["detail"]:
                        print(f"     {r['detail']}")
        return self.tests_passed == self.tests_run


def login(email, password=PASSWORD):
    """Login and return access token."""
    try:
        r = requests.post(f"{API_URL}/auth/login", 
                         json={"email": email, "password": password}, 
                         timeout=10)
        r.raise_for_status()
        return r.json()["access_token"]
    except Exception as e:
        print(f"❌ Login failed for {email}: {e}")
        return None


async def test_websocket_valid_token(runner):
    """Test 1: WebSocket with valid token returns hello event."""
    print("\n--- Test 1: WebSocket Valid Token ---")
    token = login(OWNER_EMAIL)
    if not token:
        runner.check("WS valid token - login", False, "Failed to get token")
        return

    try:
        url = f"{WS_URL}?token={token}"
        async with websockets.connect(url, open_timeout=10) as ws:
            hello = json.loads(await asyncio.wait_for(ws.recv(), timeout=8))
            runner.check("WS valid token: hello event", 
                        hello.get("event") == "hello",
                        f"Got: {hello}")
            runner.check("WS valid token: unread is int", 
                        isinstance(hello.get("unread"), int),
                        f"unread={hello.get('unread')}")
            runner.check("WS valid token: transport=websocket", 
                        hello.get("transport") == "websocket",
                        f"transport={hello.get('transport')}")
    except Exception as e:
        runner.check("WS valid token connection", False, str(e))


async def test_websocket_invalid_token(runner):
    """Test 2: WebSocket with invalid token should close with 4401."""
    print("\n--- Test 2: WebSocket Invalid Token ---")
    
    # Test with empty token
    try:
        url = f"{WS_URL}?token="
        async with websockets.connect(url, open_timeout=10) as ws:
            try:
                # Should not receive hello, should close immediately
                msg = await asyncio.wait_for(ws.recv(), timeout=3)
                runner.check("WS invalid token (empty): should close", False, 
                           f"Unexpectedly received: {msg}")
            except websockets.exceptions.ConnectionClosedError as e:
                runner.check("WS invalid token (empty): closes with 4401", 
                           e.code == 4401,
                           f"Close code: {e.code}")
    except websockets.exceptions.ConnectionClosedError as e:
        runner.check("WS invalid token (empty): closes with 4401", 
                   e.code == 4401,
                   f"Close code: {e.code}")
    except Exception as e:
        runner.check("WS invalid token (empty)", False, str(e))

    # Test with invalid token
    try:
        url = f"{WS_URL}?token=invalid_token_xyz"
        async with websockets.connect(url, open_timeout=10) as ws:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=3)
                runner.check("WS invalid token (bad): should close", False, 
                           f"Unexpectedly received: {msg}")
            except websockets.exceptions.ConnectionClosedError as e:
                runner.check("WS invalid token (bad): closes with 4401", 
                           e.code == 4401,
                           f"Close code: {e.code}")
    except websockets.exceptions.ConnectionClosedError as e:
        runner.check("WS invalid token (bad): closes with 4401", 
                   e.code == 4401,
                   f"Close code: {e.code}")
    except Exception as e:
        runner.check("WS invalid token (bad)", False, str(e))


async def test_websocket_heartbeat(runner):
    """Test 3: Heartbeat ping→pong."""
    print("\n--- Test 3: WebSocket Heartbeat ---")
    token = login(OWNER_EMAIL)
    if not token:
        runner.check("WS heartbeat - login", False, "Failed to get token")
        return

    try:
        url = f"{WS_URL}?token={token}"
        async with websockets.connect(url, open_timeout=10) as ws:
            # Consume hello
            await ws.recv()
            
            # Send ping
            await ws.send(json.dumps({"action": "ping"}))
            pong = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            runner.check("WS heartbeat: ping→pong", 
                        pong.get("event") == "pong",
                        f"Got: {pong}")
    except Exception as e:
        runner.check("WS heartbeat", False, str(e))


async def test_websocket_instant_push(runner):
    """Test 4: Instant push when notification is created."""
    print("\n--- Test 4: WebSocket Instant Push ---")
    token = login(OWNER_EMAIL)
    if not token:
        runner.check("WS instant push - login", False, "Failed to get token")
        return

    try:
        url = f"{WS_URL}?token={token}"
        async with websockets.connect(url, open_timeout=10) as ws:
            # Consume hello
            hello = json.loads(await ws.recv())
            initial_unread = hello.get("unread", 0)
            
            # Trigger notification via activity with mention
            headers = {"Authorization": f"Bearer {token}"}
            r = requests.post(f"{API_URL}/activities", 
                            headers=headers,
                            json={
                                "entity_type": "lead",
                                "entity_id": "test-instant-push",
                                "body": f"Test instant push @{OWNER_EMAIL}",
                                "type": "comment",
                                "mentions": [OWNER_EMAIL]
                            },
                            timeout=10)
            r.raise_for_status()
            
            # Wait for notification push
            got_notification = False
            for _ in range(5):
                try:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=8))
                    if msg.get("event") == "notification":
                        got_notification = True
                        runner.check("WS instant push: notification received", True,
                                   f"title={msg.get('data', {}).get('title')}")
                        runner.check("WS instant push: has data object", 
                                   isinstance(msg.get("data"), dict),
                                   f"data type: {type(msg.get('data'))}")
                        runner.check("WS instant push: unread count is int", 
                                   isinstance(msg.get("unread"), int),
                                   f"unread={msg.get('unread')}")
                        break
                except asyncio.TimeoutError:
                    break
            
            if not got_notification:
                runner.check("WS instant push: notification received", False, 
                           "No notification event within timeout")
    except Exception as e:
        runner.check("WS instant push", False, str(e))


async def test_websocket_mark_all_read(runner):
    """Test 5: mark_all_read action."""
    print("\n--- Test 5: WebSocket mark_all_read ---")
    token = login(OWNER_EMAIL)
    if not token:
        runner.check("WS mark_all_read - login", False, "Failed to get token")
        return

    try:
        url = f"{WS_URL}?token={token}"
        async with websockets.connect(url, open_timeout=10) as ws:
            # Consume hello
            await ws.recv()
            
            # Send mark_all_read
            await ws.send(json.dumps({"action": "mark_all_read"}))
            
            # Wait for unread event
            got_response = False
            for _ in range(3):
                try:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
                    if msg.get("event") == "unread":
                        got_response = True
                        runner.check("WS mark_all_read: returns unread event", True,
                                   f"Got: {msg}")
                        runner.check("WS mark_all_read: unread=0", 
                                   msg.get("unread") == 0,
                                   f"unread={msg.get('unread')}")
                        break
                except asyncio.TimeoutError:
                    break
            
            if not got_response:
                runner.check("WS mark_all_read: returns unread event", False,
                           "No unread event within timeout")
    except Exception as e:
        runner.check("WS mark_all_read", False, str(e))


async def test_websocket_mark_read(runner):
    """Test 6: mark_read individual notification."""
    print("\n--- Test 6: WebSocket mark_read ---")
    token = login(SALES_EMAIL)
    if not token:
        runner.check("WS mark_read - login", False, "Failed to get token")
        return

    try:
        # First create a notification for sales user
        headers = {"Authorization": f"Bearer {token}"}
        r = requests.post(f"{API_URL}/activities",
                        headers=headers,
                        json={
                            "entity_type": "lead",
                            "entity_id": "test-mark-read",
                            "body": f"Test mark_read @{SALES_EMAIL}",
                            "type": "comment",
                            "mentions": [SALES_EMAIL]
                        },
                        timeout=10)
        r.raise_for_status()
        
        # Get the notification ID
        time.sleep(0.5)  # Brief wait for notification to be created
        r = requests.get(f"{API_URL}/notifications?limit=1", headers=headers, timeout=10)
        r.raise_for_status()
        notifications = r.json().get("data", [])
        
        if not notifications:
            runner.check("WS mark_read: create notification", False, "No notification created")
            return
        
        notif_id = notifications[0].get("id")
        initial_unread = r.json().get("unread", 0)
        
        # Connect WebSocket and mark as read
        url = f"{WS_URL}?token={token}"
        async with websockets.connect(url, open_timeout=10) as ws:
            # Consume hello and any pending notifications
            await ws.recv()
            
            # Send mark_read
            await ws.send(json.dumps({"action": "mark_read", "id": notif_id}))
            
            # Wait for unread event
            got_response = False
            for _ in range(3):
                try:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
                    if msg.get("event") == "unread":
                        got_response = True
                        runner.check("WS mark_read: returns unread event", True,
                                   f"Got: {msg}")
                        runner.check("WS mark_read: unread count decreased", 
                                   isinstance(msg.get("unread"), int) and msg.get("unread") < initial_unread,
                                   f"unread: {initial_unread} → {msg.get('unread')}")
                        break
                except asyncio.TimeoutError:
                    break
            
            if not got_response:
                runner.check("WS mark_read: returns unread event", False,
                           "No unread event within timeout")
    except Exception as e:
        runner.check("WS mark_read", False, str(e))


async def test_sse_fallback(runner):
    """Test 7: SSE fallback /api/notifications/stream."""
    print("\n--- Test 7: SSE Fallback ---")
    token = login(FINANCE_EMAIL)
    if not token:
        runner.check("SSE fallback - login", False, "Failed to get token")
        return

    try:
        url = f"{API_URL}/notifications/stream?token={token}"
        r = requests.get(url, stream=True, timeout=10)
        
        runner.check("SSE fallback: status 200", 
                    r.status_code == 200,
                    f"Status: {r.status_code}")
        runner.check("SSE fallback: content-type text/event-stream",
                    "text/event-stream" in r.headers.get("content-type", ""),
                    f"Content-Type: {r.headers.get('content-type')}")
        
        # Read first event (should be hello)
        got_hello = False
        for line in r.iter_lines(decode_unicode=True):
            if line.startswith("event: hello"):
                got_hello = True
            elif line.startswith("data: ") and got_hello:
                data = json.loads(line[6:])
                runner.check("SSE fallback: hello event received", True,
                           f"data={data}")
                runner.check("SSE fallback: hello has unread", 
                           "unread" in data,
                           f"data={data}")
                break
        
        if not got_hello:
            runner.check("SSE fallback: hello event received", False,
                       "No hello event in stream")
        
        r.close()
    except Exception as e:
        runner.check("SSE fallback", False, str(e))


def test_regression_login(runner):
    """Test 8a: Regression - login works for seeded users."""
    print("\n--- Test 8a: Regression - Login ---")
    
    for email in [OWNER_EMAIL, SALES_EMAIL, FINANCE_EMAIL, "sales2@sipro.co.id"]:
        token = login(email)
        runner.check(f"Login: {email}", 
                    token is not None,
                    "Got access token" if token else "Failed to get token")


def test_regression_work_home(runner):
    """Test 8b: Regression - GET /api/work/home."""
    print("\n--- Test 8b: Regression - /api/work/home ---")
    token = login(OWNER_EMAIL)
    if not token:
        runner.check("work/home - login", False, "Failed to get token")
        return

    try:
        headers = {"Authorization": f"Bearer {token}"}
        r = requests.get(f"{API_URL}/work/home", headers=headers, timeout=10)
        runner.check("GET /api/work/home: status 200", 
                    r.status_code == 200,
                    f"Status: {r.status_code}")
        
        if r.status_code == 200:
            response = r.json()
            data = response.get("data", {})
            runner.check("GET /api/work/home: has title", 
                        "title" in data,
                        f"title={data.get('title')}")
            runner.check("GET /api/work/home: has kpis", 
                        "kpis" in data,
                        f"kpis count={len(data.get('kpis', []))}")
            runner.check("GET /api/work/home: has tasks", 
                        "tasks" in data,
                        f"tasks keys={list(data.get('tasks', {}).keys())}")
    except Exception as e:
        runner.check("GET /api/work/home", False, str(e))


def test_regression_notifications(runner):
    """Test 8c: Regression - GET /api/notifications."""
    print("\n--- Test 8c: Regression - /api/notifications ---")
    token = login(OWNER_EMAIL)
    if not token:
        runner.check("notifications - login", False, "Failed to get token")
        return

    try:
        headers = {"Authorization": f"Bearer {token}"}
        r = requests.get(f"{API_URL}/notifications", headers=headers, timeout=10)
        runner.check("GET /api/notifications: status 200", 
                    r.status_code == 200,
                    f"Status: {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            runner.check("GET /api/notifications: has data", 
                        "data" in data,
                        f"Keys: {list(data.keys())}")
            runner.check("GET /api/notifications: has unread", 
                        "unread" in data,
                        f"Keys: {list(data.keys())}")
    except Exception as e:
        runner.check("GET /api/notifications", False, str(e))


def test_regression_rbac(runner):
    """Test 8d: Regression - RBAC (sales -> admin/users = 403, owner = 200)."""
    print("\n--- Test 8d: Regression - RBAC ---")
    
    # Sales user should get 403
    sales_token = login(SALES_EMAIL)
    if sales_token:
        try:
            headers = {"Authorization": f"Bearer {sales_token}"}
            r = requests.get(f"{API_URL}/admin/users", headers=headers, timeout=10)
            runner.check("RBAC: sales -> GET /api/admin/users = 403", 
                        r.status_code == 403,
                        f"Status: {r.status_code}")
        except Exception as e:
            runner.check("RBAC: sales -> admin/users", False, str(e))
    
    # Owner should get 200
    owner_token = login(OWNER_EMAIL)
    if owner_token:
        try:
            headers = {"Authorization": f"Bearer {owner_token}"}
            r = requests.get(f"{API_URL}/admin/users", headers=headers, timeout=10)
            runner.check("RBAC: owner -> GET /api/admin/users = 200", 
                        r.status_code == 200,
                        f"Status: {r.status_code}")
        except Exception as e:
            runner.check("RBAC: owner -> admin/users", False, str(e))


async def run_all_tests():
    """Run all tests."""
    runner = TestRunner()
    
    print("=" * 70)
    print("EPIC M3 WebSocket Notifications - Comprehensive Backend Test")
    print("=" * 70)
    
    # WebSocket tests
    await test_websocket_valid_token(runner)
    await test_websocket_invalid_token(runner)
    await test_websocket_heartbeat(runner)
    await test_websocket_instant_push(runner)
    await test_websocket_mark_all_read(runner)
    await test_websocket_mark_read(runner)
    
    # SSE fallback
    await test_sse_fallback(runner)
    
    # Regression tests
    test_regression_login(runner)
    test_regression_work_home(runner)
    test_regression_notifications(runner)
    test_regression_rbac(runner)
    
    # Summary
    success = runner.print_summary()
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(run_all_tests())
    sys.exit(exit_code)
