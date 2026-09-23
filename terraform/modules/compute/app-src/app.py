import json
import logging
import os
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from flask import Flask, render_template_string

app = Flask(__name__)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))


def read_text(path: str, fallback: str = "unknown") -> str:
    try:
        return Path(path).read_text().strip() or fallback
    except OSError:
        return fallback


@app.get("/")
def index():
    az = read_text("/var/lib/app/az.txt")
    instance_id = read_text("/var/lib/app/instance-id.txt")
    return render_template_string(
        """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Client Platform</title></head>
<body>
  <main>
    <h1>Secure, Highly Available Web Platform</h1>
    <p>Served by Availability Zone: <strong>{{ az }}</strong></p>
    <p>Instance: <strong>{{ instance_id }}</strong></p>
  </main>
</body>
</html>""",
        az=az,
        instance_id=instance_id,
    )


@app.get("/health")
def health():
    # Keep the ALB health check independent from the database.
    return "OK", 200, {"Content-Type": "text/plain; charset=utf-8"}


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000)
