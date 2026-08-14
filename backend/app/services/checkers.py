import platform
import socket
import ssl
import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

import httpx
import dns.resolver

from app.core.config import settings
from app.models.asset import Asset


@dataclass
class CheckResult:
    status: str
    target: str
    response_time: float | None = None
    message: str | None = None
    error_message: str | None = None


class BaseChecker(ABC):
    check_type: str

    @abstractmethod
    def check(self, asset: Asset) -> list[CheckResult]:
        pass


class PingChecker(BaseChecker):
    check_type = "ping"

    def check(self, asset: Asset) -> list[CheckResult]:
        start = time.monotonic()
        command = ["ping", "-n" if platform.system() == "Windows" else "-c", "1", asset.ip]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=settings.ping_timeout,
                check=False,
            )
            elapsed = round((time.monotonic() - start) * 1000, 2)
            if completed.returncode == 0:
                return [CheckResult("success", asset.ip, elapsed, "Ping 成功")]
            return [CheckResult("failed", asset.ip, elapsed, error_message="Ping 不可达")]
        except Exception as exc:
            return [CheckResult("failed", asset.ip, error_message=str(exc))]


class PortChecker(BaseChecker):
    check_type = "port"

    def check(self, asset: Asset) -> list[CheckResult]:
        ports = [int(value.strip()) for value in (asset.ports or "").split(",") if value.strip().isdigit() and 1 <= int(value.strip()) <= 65535]
        if not ports:
            return [CheckResult("failed", asset.ip, error_message="未配置合法端口")]
        results = []
        for port in ports:
            target = f"{asset.ip}:{port}"
            start = time.monotonic()
            try:
                with socket.create_connection((asset.ip, port), timeout=settings.tcp_timeout):
                    elapsed = round((time.monotonic() - start) * 1000, 2)
                    results.append(CheckResult("success", target, elapsed, "端口开放"))
            except Exception as exc:
                elapsed = round((time.monotonic() - start) * 1000, 2)
                results.append(CheckResult("failed", target, elapsed, error_message=str(exc)))
        return results


class HttpChecker(BaseChecker):
    check_type = "http"

    def check(self, asset: Asset) -> list[CheckResult]:
        ports = [int(value.strip()) for value in (asset.ports or "").split(",") if value.strip().isdigit() and 1 <= int(value.strip()) <= 65535]
        port = ports[0] if ports else 80
        target = f"http://{asset.ip}:{port}" if port != 80 else f"http://{asset.ip}"
        start = time.monotonic()
        try:
            response = httpx.get(target, timeout=settings.http_timeout)
            elapsed = round((time.monotonic() - start) * 1000, 2)
            if response.is_success:
                result_status = "warning" if elapsed > settings.slow_response_threshold else "success"
                message = f"HTTP {response.status_code}" + ("，响应缓慢" if result_status == "warning" else "")
                return [CheckResult(result_status, target, elapsed, message)]
            return [CheckResult("failed", target, elapsed, error_message=f"HTTP {response.status_code}")]
        except Exception as exc:
            return [CheckResult("failed", target, error_message=str(exc))]


class DnsChecker(BaseChecker):
    check_type = "dns"

    def check(self, asset: Asset) -> list[CheckResult]:
        target = asset.hostname or asset.ip
        start = time.monotonic()
        try:
            answers = dns.resolver.resolve(target, "A", lifetime=settings.tcp_timeout)
            elapsed = round((time.monotonic() - start) * 1000, 2)
            addresses = ",".join(answer.to_text() for answer in answers)
            status = "warning" if elapsed > settings.slow_response_threshold else "success"
            message = "DNS 解析成功" + ("，响应缓慢" if status == "warning" else "")
            if addresses:
                message = f"{message}: {addresses}"
            return [CheckResult(status, target, elapsed, message)]
        except Exception as exc:
            elapsed = round((time.monotonic() - start) * 1000, 2)
            return [CheckResult("failed", target, elapsed, error_message=str(exc))]


class TlsChecker(BaseChecker):
    """TLS 证书检测：连接 HTTPS 端口，校验证书有效期。

    - 优先使用资产配置的端口（含 443/8443 等 TLS 端口），未配置时默认探测 443；
    - 证书剩余天数低于 tls_expiry_warning_days 判定为 warning，已过期判定为 failed。
    """

    check_type = "tls"

    def check(self, asset: Asset) -> list[CheckResult]:
        configured = [int(value.strip()) for value in (asset.ports or "").split(",") if value.strip().isdigit() and 1 <= int(value.strip()) <= 65535]
        tls_ports = [port for port in configured if port in (443, 8443, 9443)]
        # 资产配置了 TLS 端口就用它，否则默认探测 443
        ports = tls_ports or [443]
        results = []
        for port in ports:
            target = f"{asset.ip}:{port}"
            start = time.monotonic()
            try:
                context = ssl.create_default_context()
                with socket.create_connection((asset.ip, port), timeout=settings.tcp_timeout) as raw:
                    with context.wrap_socket(raw, server_hostname=asset.hostname or asset.ip) as sock:
                        cert = sock.getpeercert()
                        elapsed = round((time.monotonic() - start) * 1000, 2)
                        if not cert:
                            results.append(CheckResult("warning", target, elapsed, "TLS 握手成功但未取得证书信息"))
                            continue
                        not_after = cert.get("notAfter", "")
                        expires_at = _parse_cert_time(not_after)
                        if expires_at is None:
                            results.append(CheckResult("success", target, elapsed, f"TLS 握手成功（证书解析失败: {not_after}）"))
                            continue
                        days_left = (expires_at - datetime.now()).days
                        issuer = dict(cert.get("issuer", [])).get("commonName", "") or dict(cert.get("issuer", [])).get("organizationName", "") or "未知"
                        if days_left < 0:
                            results.append(CheckResult("failed", target, elapsed, error_message=f"TLS 证书已过期 {-days_left} 天（{not_after}）"))
                        elif days_left <= settings.tls_expiry_warning_days:
                            results.append(CheckResult("warning", target, elapsed, f"TLS 证书即将过期，剩余 {days_left} 天（{not_after}）"))
                        else:
                            results.append(CheckResult("success", target, elapsed, f"TLS 证书有效，剩余 {days_left} 天（签发者 {issuer}）"))
            except Exception as exc:
                elapsed = round((time.monotonic() - start) * 1000, 2)
                results.append(CheckResult("failed", target, elapsed, error_message=str(exc)))
        return results


def _parse_cert_time(value: str) -> datetime | None:
    """解析证书 notAfter 时间（如 'Aug 14 09:30:00 2026 GMT'）。"""
    try:
        return datetime.strptime(value.strip(), "%b %d %H:%M:%S %Y %Z")
    except ValueError:
        try:
            import email.utils

            parsed = email.utils.parsedate_to_datetime(value.strip())
            return parsed.replace(tzinfo=None)
        except Exception:
            return None


CHECKERS = {checker.check_type: checker for checker in (PingChecker(), PortChecker(), HttpChecker(), DnsChecker(), TlsChecker())}
