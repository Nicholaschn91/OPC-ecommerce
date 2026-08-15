#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Minimal CORS-enabled static server to serve dp_run/ files to the qianwen.com
browser (for one-time localStorage seeding of the SI constant)."""
import http.server
import os
import socketserver

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/dp_run"
PORT = 18765


class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=ROOT, **k)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def log_message(self, *a, **k):
        pass


with socketserver.TCPServer(("127.0.0.1", PORT), H) as s:
    s.serve_forever()
