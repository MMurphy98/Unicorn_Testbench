#!/usr/bin/env python3
"""Read-only thermal-stream Modbus TCP probe; Python standard library only."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import socket
import struct
import sys


PROJECT_DIR = Path(__file__).resolve().parents[1]
READS = (
    ("air_temperature_c", 0x03, 0),
    ("product_temperature_c", 0x03, 1),
    ("running", 0x01, 10),
)


class ProtocolError(Exception):
    """The peer did not return the requested Modbus response."""


def receive_exact(sock: socket.socket, count: int, captured: bytearray) -> bytes:
    data = bytearray()
    while len(data) < count:
        chunk = sock.recv(count - len(data))
        if not chunk:
            raise ProtocolError("Peer closed the connection before a complete response")
        data.extend(chunk)
        captured.extend(chunk)
    return bytes(data)


def read_one(sock: socket.socket, unit_id: int, name: str,
             function: int, address: int) -> dict:
    if function not in (0x01, 0x03):
        raise ValueError("This probe permits only read functions 01 and 03")
    # The vendor examples use transaction ID 0 and unit ID 0. Requests are
    # strictly sequential, so there is never more than one outstanding request.
    request = struct.pack(">HHHBBHH", 0, 0, 6, unit_id, function, address, 1)
    record = {
        "name": name, "function": function, "address": address,
        "request_hex": request.hex(" ").upper(), "ok": False,
    }
    received = bytearray()
    print(f"TX {name}: {record['request_hex']}")
    try:
        sock.sendall(request)
        header = receive_exact(sock, 7, received)
        transaction, protocol, length, response_unit = struct.unpack(">HHHB", header)
        if not 2 <= length <= 254:
            raise ProtocolError(f"Invalid MBAP length: {length}")
        pdu = receive_exact(sock, length - 1, received)
        if (transaction, protocol, response_unit) != (0, 0, unit_id):
            raise ProtocolError(
                f"Unexpected MBAP header: transaction={transaction}, "
                f"protocol={protocol}, unit={response_unit}"
            )
        if pdu[0] == function | 0x80:
            if len(pdu) != 2:
                raise ProtocolError("Malformed Modbus exception response")
            record["exception_code"] = pdu[1]
            raise ProtocolError(f"Modbus exception code {pdu[1]}")
        expected_bytes = 2 if function == 0x03 else 1
        if (len(pdu) != expected_bytes + 2 or pdu[0] != function
                or pdu[1] != expected_bytes):
            raise ProtocolError(f"Unexpected response PDU: {pdu.hex(' ')}")
        raw = int.from_bytes(pdu[2:], "big")
        if function == 0x03:
            signed = raw if raw < 0x8000 else raw - 0x10000
            value = signed / 10.0
        else:
            value = bool(raw & 1)
        record.update(ok=True, raw=raw, value=value)
    except (OSError, ProtocolError) as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
    record["response_hex"] = received.hex(" ").upper()
    print(f"RX {name}: {record['response_hex'] or '(no bytes)'}")
    if record["ok"]:
        print(f"  {name} = {record['value']}")
    else:
        print(f"  FAILED: {record['error']}")
    return record


def positive_timeout(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("timeout must be positive and finite")
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="192.168.1.50",
                        help="Actual device communication IP; manual example is .55")
    parser.add_argument("--port", type=int, default=3000)
    parser.add_argument("--unit-id", type=int, default=0)
    parser.add_argument("--timeout", type=positive_timeout, default=3.0,
                        help="Socket connect/receive timeout in seconds")
    parser.add_argument("--source-ip", help="Optional PC interface IPv4 address")
    parser.add_argument("--output", type=Path, help="JSON report path")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("port must be in 1..65535")
    if not 0 <= args.unit_id <= 255:
        parser.error("unit-id must be in 0..255")

    now = datetime.now(timezone.utc)
    output = args.output or (
        PROJECT_DIR / "results" / "thermal_stream"
        / f"tcp_probe_{now.strftime('%Y%m%dT%H%M%S_%fZ')}.json"
    )
    report = {
        "started_at_utc": now.isoformat(),
        "target": {"host": args.host, "port": args.port, "unit_id": args.unit_id},
        "source_ip": args.source_ip, "timeout_seconds": args.timeout,
        "read_only": True, "tcp_connected": False,
        "reads": [], "ok": False,
    }
    print(f"Read-only probe: {args.host}:{args.port}, unit ID {args.unit_id}")
    try:
        source = (args.source_ip, 0) if args.source_ip else None
        with socket.create_connection((args.host, args.port), args.timeout,
                                      source_address=source) as sock:
            report["tcp_connected"] = True
            report["local_endpoint"] = list(sock.getsockname())
            report["remote_endpoint"] = list(sock.getpeername())
            print(f"TCP CONNECTED: {sock.getsockname()} -> {sock.getpeername()}")
            for name, function, address in READS:
                record = read_one(sock, args.unit_id, name, function, address)
                report["reads"].append(record)
                # On error, do not reuse a possibly desynchronised TCP stream.
                if not record["ok"]:
                    break
            report["ok"] = (
                len(report["reads"]) == len(READS)
                and all(record["ok"] for record in report["reads"])
            )
    except OSError as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        print(f"FAILED: {report['error']}")

    report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(f"JSON report: {output.resolve()}")
    if report["ok"]:
        print("PASS: TCP connection and all three read requests succeeded")
        return 0
    return 2 if report["tcp_connected"] else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
