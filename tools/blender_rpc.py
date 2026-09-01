"""Talks to the live Blender started by tools/blender_live.py.

    python tools/blender_rpc.py "import bpy; print(len(bpy.data.objects))"
    python tools/blender_rpc.py --file some_script.py

The headless render is what ships and should stay that way. This is the other
half: a way to look at a part from an angle, check that a chamfer followed the
edge it was meant to, and turn a shape over BEFORE committing eight minutes to
rendering it. Straight-down orthographic hides exactly the errors that matter in
a turned part, so being able to tilt the camera is not a luxury.

Same socket the MCP server uses, so nothing here is a private back door - it is
the addon's own protocol, and this works whether or not the MCP client happens
to be connected.
"""

import json
import socket
import sys

HOST, PORT = "127.0.0.1", 9876


def call(cmd, params=None, timeout=180):
    """One command, one reply. The addon answers with a single JSON object and
    then waits, so read until the buffer parses rather than until EOF."""
    s = socket.create_connection((HOST, PORT), timeout=timeout)
    try:
        s.sendall(json.dumps({"type": cmd, "params": params or {}}).encode())
        buf = b""
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
            try:
                return json.loads(buf.decode())
            except json.JSONDecodeError:
                continue
        return json.loads(buf.decode())
    finally:
        s.close()


def run(code, timeout=180):
    """Execute python inside Blender and hand back whatever it printed."""
    reply = call("execute_code", {"code": code}, timeout)
    if reply.get("status") != "success":
        raise RuntimeError(reply.get("message") or json.dumps(reply)[:400])
    return reply.get("result", {}).get("result", "")


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--file":
        with open(sys.argv[2]) as f:
            code = f.read()
    elif len(sys.argv) > 1:
        code = sys.argv[1]
    else:
        print(__doc__)
        return 0
    try:
        print(run(code), end="")
    except (OSError, RuntimeError) as exc:
        print("blender is not answering on %s:%d - start it with "
              "tools/blender_live.py\n  %s" % (HOST, PORT, exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
