from __future__ import annotations

import html
import ipaddress
import re
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

import requests


MAX_RESPONSE_BYTES = 1_000_000
TIMEOUT_SECONDS = 8
MAX_REDIRECTS = 3
BLOCKED_METADATA_IPS = {
    ipaddress.ip_address('169.254.169.254'),
}


class JDURLAnalysisError(ValueError):
    code = 'JD_URL_ANALYSIS_FAILED'


class JDURLBlocked(JDURLAnalysisError):
    code = 'JD_URL_BLOCKED'


class JDURLFetchFailed(JDURLAnalysisError):
    code = 'JD_URL_FETCH_FAILED'


@dataclass(frozen=True)
class JDURLAnalysisResult:
    source_url: str
    raw_text: str
    extracted_fields: dict
    confidence: float


def _is_blocked_ip(ip: str) -> bool:
    parsed = ipaddress.ip_address(ip)
    return (
        parsed.is_loopback
        or parsed.is_private
        or parsed.is_link_local
        or parsed.is_multicast
        or parsed.is_reserved
        or parsed in BLOCKED_METADATA_IPS
    )


def validate_public_url(url: str) -> str:
    normalized = (url or '').strip()
    parsed = urlparse(normalized)
    if parsed.scheme not in {'http', 'https'}:
        raise JDURLBlocked('Only http and https URLs are allowed.')
    if not parsed.hostname:
        raise JDURLBlocked('URL host is required.')
    hostname = parsed.hostname.lower()
    if hostname in {'localhost', 'metadata.google.internal'} or hostname.endswith('.local'):
        raise JDURLBlocked('Local or metadata hosts are blocked.')
    try:
        addresses = socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == 'https' else 80))
    except socket.gaierror as exc:
        raise JDURLBlocked('URL host could not be resolved.') from exc
    for address in addresses:
        ip = address[4][0]
        if _is_blocked_ip(ip):
            raise JDURLBlocked('Private, local, or metadata IP addresses are blocked.')
    return normalized


def _strip_html(raw_html: str) -> str:
    clean = re.sub(r'(?is)<(script|style|noscript).*?>.*?</\1>', ' ', raw_html)
    clean = re.sub(r'(?is)<br\s*/?>', '\n', clean)
    clean = re.sub(r'(?is)</(p|div|li|h[1-6]|tr)>', '\n', clean)
    clean = re.sub(r'(?is)<[^>]+>', ' ', clean)
    clean = html.unescape(clean)
    clean = re.sub(r'[ \t\r\f\v]+', ' ', clean)
    clean = re.sub(r'\n\s+', '\n', clean)
    return clean.strip()


def _first_line_matching(text: str, patterns: list[str]) -> str:
    for line in text.splitlines():
        normalized = line.strip()
        if not normalized:
            continue
        for pattern in patterns:
            if re.search(pattern, normalized, re.I):
                return normalized[:200]
    return ''


def extract_job_fields(text: str, source_url: str) -> dict:
    title = _first_line_matching(text, [r'(developer|engineer|backend|frontend|data|ai|ml|개발|엔지니어|채용|공고)'])
    company = _first_line_matching(text, [r'(주식회사|회사|corp|inc|ltd|career|recruit)'])
    stack_candidates = re.findall(
        r'\b(Python|Django|FastAPI|Java|Spring|React|Vue|TypeScript|JavaScript|Node\.js|MySQL|PostgreSQL|AWS|Docker|Kubernetes|Redis)\b',
        text,
        flags=re.I,
    )
    skills = []
    for item in stack_candidates:
        label = item.strip()
        if label and label.lower() not in {s.lower() for s in skills}:
            skills.append(label)
    confidence = 0.35
    if title:
        confidence += 0.2
    if company:
        confidence += 0.15
    if skills:
        confidence += 0.2
    return {
        'company_name': company[:100] or 'Unspecified company',
        'position': title[:100] or 'Unspecified position',
        'experience': _first_line_matching(text, [r'(경력|신입|junior|senior|년 이상)']),
        'employment_type': _first_line_matching(text, [r'(정규직|계약직|인턴|full.?time|contract)']),
        'tech_stacks': skills[:20],
        'main_tasks': _first_line_matching(text, [r'(주요 업무|담당 업무|responsibilit|what you will do)']),
        'requirements': _first_line_matching(text, [r'(자격 요건|지원 자격|required|qualification)']),
        'preferences': _first_line_matching(text, [r'(우대|preferred|nice to have)']),
        'location': _first_line_matching(text, [r'(근무지|location|서울|경기|판교|remote)']),
        'source_url': source_url,
        'confidence': round(min(confidence, 0.95), 2),
    }


def analyze_job_url(url: str) -> JDURLAnalysisResult:
    safe_url = validate_public_url(url)
    session = requests.Session()
    session.max_redirects = MAX_REDIRECTS
    try:
        response = session.get(
            safe_url,
            timeout=TIMEOUT_SECONDS,
            stream=True,
            headers={'User-Agent': 'CareerZip-JD-Analyzer/1.0'},
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise JDURLFetchFailed('Unable to fetch the provided URL.') from exc

    final_url = validate_public_url(response.url)
    content_type = (response.headers.get('content-type') or '').lower()
    if 'text/html' not in content_type and 'application/xhtml+xml' not in content_type:
        raise JDURLBlocked('Only public HTML job pages can be analyzed.')

    chunks = []
    total = 0
    for chunk in response.iter_content(chunk_size=8192, decode_unicode=False):
        if not chunk:
            continue
        total += len(chunk)
        if total > MAX_RESPONSE_BYTES:
            raise JDURLBlocked('URL response is too large.')
        chunks.append(chunk)
    raw_html = b''.join(chunks).decode(response.encoding or 'utf-8', errors='replace')
    text = _strip_html(raw_html)
    if not text:
        raise JDURLFetchFailed('No text content could be extracted from the URL.')
    fields = extract_job_fields(text, final_url)
    return JDURLAnalysisResult(
        source_url=final_url,
        raw_text=text[:20000],
        extracted_fields=fields,
        confidence=fields['confidence'],
    )
