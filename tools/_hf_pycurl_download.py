# -*- coding: utf-8 -*-
"""
Загрузчик моделей HuggingFace через pycurl + HTTP API Hub'а для портативной
сборки UniMate. Замена нестабильного hf.exe: список файлов берётся из
публичного tree-API, сами файлы качаются напрямую через pycurl (libcurl)
с докачкой (.part + Range) и повторами.

FModel.Cli/scripts/_hf_pycurl_download.py
Version:     1.1.0
Author:      Soror L.'.L.'.
Updated:     2026-10-17

Patch Notes v1.1.0 (Soror L.'.L.'.):
  [+] --include / --exclude glob-фильтры (повторяемые): градация
      чекпоинтов по востребованию - качаем только нужные файлы репо.
  [+] Тег [HF] в сообщениях; путь .part остаётся рядом с целью.
  [*] Адаптация под портативную сборку UniMate.

Использование:
    python _hf_pycurl_download.py <repo_id> <local_dir>
        [--revision main] [--repo-type model|dataset|space]
        [--include GLOB ...] [--exclude GLOB ...] [--token <hf_token>]
"""

import argparse
import fnmatch
import json
import os
import sys
import time
from io import BytesIO
from urllib.parse import quote, urljoin, urlparse

from tqdm import tqdm

try:
    import pycurl
except ImportError:
    sys.stderr.write(
        "[HF] ОШИБКА: модуль 'pycurl' не установлен.\n"
        "            Установите его: uv pip install pycurl\n"
    )
    sys.exit(2)


ENDPOINT = os.environ.get("HF_ENDPOINT", "https://huggingface.co").rstrip("/")
USER_AGENT = "unimate-pycurl/1.1 (+libcurl)"
CONNECT_TIMEOUT = 30
LOW_SPEED_LIMIT = 1024        # байт/сек: если медленнее...
LOW_SPEED_TIME = 60           # ...в течение стольких секунд - обрыв и повтор
MAX_ATTEMPTS = 5
MAX_REDIRECTS = 10


# --------------------------------------------------------------------------- #
# SSL / CA
# --------------------------------------------------------------------------- #
def _detect_cainfo():
    """Для сборок libcurl на OpenSSL/GnuTLS указываем CA-бандл из certifi.

    Сборки на нативном Schannel (типичны для Windows-wheel'ов pycurl) берут
    доверенные корни из хранилища Windows и CAINFO игнорируют - тогда ничего
    не задаём, чтобы не спровоцировать ошибку.
    """
    try:
        ssl_backend = (pycurl.version_info()[5] or "").lower()
    except Exception:
        ssl_backend = ""
    if any(name in ssl_backend for name in ("openssl", "libressl", "boringssl",
                                            "gnutls", "mbedtls", "wolfssl")):
        try:
            import certifi
            return certifi.where()
        except Exception:
            return None
    return None


_CAINFO = _detect_cainfo()


def _apply_common(c, token, host_is_hf, resume_pos=0):
    c.setopt(pycurl.USERAGENT, USER_AGENT)
    c.setopt(pycurl.CONNECTTIMEOUT, CONNECT_TIMEOUT)
    c.setopt(pycurl.NOSIGNAL, 1)
    c.setopt(pycurl.TCP_KEEPALIVE, 1)
    if _CAINFO:
        try:
            c.setopt(pycurl.CAINFO, _CAINFO)
        except Exception:
            pass
    headers = ["Accept-Encoding: identity"]
    # Токен отправляем только на сам Hub, но НИКОГДА на CDN-редирект (там
    # своя подписанная ссылка, лишний Authorization вызывает 400).
    if token and host_is_hf:
        headers.append("Authorization: Bearer %s" % token)
    # Докачку задаём собственным Range-заголовком, а не RESUME_FROM_LARGE:
    # первый ответ Hub'а - это 302 на CDN, и встроенная в libcurl проверка
    # Range (ждущая 206) свалилась бы на редиректе с ошибкой 33.
    if resume_pos:
        headers.append("Range: bytes=%d-" % resume_pos)
    c.setopt(pycurl.HTTPHEADER, headers)


def _host_is_hf(url):
    host = (urlparse(url).hostname or "").lower()
    ep_host = (urlparse(ENDPOINT).hostname or "").lower()
    return host == ep_host or host.endswith(".huggingface.co") or host == "huggingface.co"


# --------------------------------------------------------------------------- #
# Фильтрация файлов (градация по востребованию)
# --------------------------------------------------------------------------- #
def _wanted(path, includes, excludes):
    """True, если файл проходит include/exclude globs.

    Без --include качается всё; --exclude всегда сильнее --include.
    """
    for pat in excludes:
        if fnmatch.fnmatch(path, pat):
            return False
    if not includes:
        return True
    return any(fnmatch.fnmatch(path, pat) for pat in includes)


# --------------------------------------------------------------------------- #
# Работа со списком файлов (tree API)
# --------------------------------------------------------------------------- #
def _api_get(url, token):
    """GET JSON. Возвращает (bytes, {rel: url}) из заголовка Link."""
    buf = BytesIO()
    headers = {}

    def _hdr(line):
        try:
            text = line.decode("iso-8859-1")
        except Exception:
            return
        if ":" in text:
            k, v = text.split(":", 1)
            headers[k.strip().lower()] = v.strip()

    c = pycurl.Curl()
    c.setopt(pycurl.URL, url)
    c.setopt(pycurl.FOLLOWLOCATION, 1)
    c.setopt(pycurl.MAXREDIRS, MAX_REDIRECTS)
    c.setopt(pycurl.WRITEDATA, buf)
    c.setopt(pycurl.HEADERFUNCTION, _hdr)
    _apply_common(c, token, host_is_hf=True)
    try:
        c.perform()
        code = c.getinfo(pycurl.RESPONSE_CODE)
    finally:
        c.close()

    if code != 200:
        snippet = buf.getvalue()[:500].decode("utf-8", "replace")
        raise RuntimeError("HF API вернул HTTP %s для %s\n%s" % (code, url, snippet))

    links = {}
    raw = headers.get("link")
    if raw:
        for part in raw.split(","):
            seg = part.split(";")
            if len(seg) < 2:
                continue
            u = seg[0].strip().lstrip("<").rstrip(">")
            for attr in seg[1:]:
                attr = attr.strip()
                if attr.startswith("rel="):
                    rel = attr[4:].strip().strip('"')
                    links[rel] = u
    return buf.getvalue(), links


def list_repo_files(repo_id, revision, repo_type, token):
    """Список (path, size) всех файлов репозитория (рекурсивно, с пагинацией)."""
    prefix = {"model": "models", "dataset": "datasets", "space": "spaces"}[repo_type]
    url = "%s/api/%s/%s/tree/%s?recursive=1" % (
        ENDPOINT, prefix, repo_id, quote(revision, safe=""))
    files = []
    while url:
        body, links = _api_get(url, token)
        for item in json.loads(body):
            if item.get("type") != "file":
                continue
            size = item.get("size")
            lfs = item.get("lfs")
            if isinstance(lfs, dict) and lfs.get("size") is not None:
                size = lfs["size"]
            files.append((item["path"], size))
        url = links.get("next")
    return files


# --------------------------------------------------------------------------- #
# Скачивание одного файла
# --------------------------------------------------------------------------- #
class _Sink:
    """Пишет тело ответа в файл; тело редиректов/ошибок отбрасывает.

    Учитывает Range: при 206 дописывает от resume_pos, при 200 (сервер Range
    проигнорировал) - перезаписывает файл с нуля. Прогресс ведёт tqdm
    (скорость, ETA, байты) - самодельный процент-бар заменён им.
    """

    def __init__(self, path, resume_pos, total, name):
        self.path = path
        self.resume_pos = resume_pos
        self.total = total or 0
        self.name = name
        self.status = None
        self.location = None
        self.fh = None
        self._base = resume_pos      # байты уже в .part до текущего ответа
        self._tqdm = None

    def header(self, line):
        try:
            text = line.decode("iso-8859-1").strip()
        except Exception:
            return
        if text.startswith("HTTP/"):
            parts = text.split()
            if len(parts) >= 2 and parts[1].isdigit():
                self.status = int(parts[1])
            self.location = None          # новый ответ в цепочке редиректов
        elif ":" in text:
            k, v = text.split(":", 1)
            if k.strip().lower() == "location":
                self.location = v.strip()

    def _open(self):
        if self.fh is not None:
            return
        if self.status == 206 and self.resume_pos:
            self.fh = open(self.path, "r+b")
            self.fh.seek(self.resume_pos)
            self._base = self.resume_pos
        else:                              # 200 или скачивание с нуля
            self.fh = open(self.path, "wb")
            self._base = 0
        self._make_bar()

    def _make_bar(self):
        """tqdm-бар поверх уже имеющихся в .part байтов (resume)."""
        total = self.total or None
        initial = self._base if total else 0
        self._tqdm = tqdm(total=total, initial=initial, unit="B", unit_scale=True,
                          unit_divisor=1024, desc="    " + self.name,
                          leave=False, dynamic_ncols=True, file=sys.stdout)

    def write(self, data):
        if self.status is None:
            return len(data)
        if 200 <= self.status < 300:
            self._open()
            self.fh.write(data)
            if self._tqdm is not None:
                self._tqdm.update(len(data))
        return len(data)                   # тело не-2xx проглатываем

    def close(self):
        if self._tqdm is not None:
            self._tqdm.close()
            self._tqdm = None
        if self.fh is not None:
            self.fh.close()
            self.fh = None


def _download_once(url, sink, token):
    """Одна попытка: ручное следование редиректам, чтобы не слать токен на CDN."""
    current = url
    for _ in range(MAX_REDIRECTS):
        sink.status = None
        sink.location = None
        c = pycurl.Curl()
        c.setopt(pycurl.URL, current)
        c.setopt(pycurl.FOLLOWLOCATION, 0)
        c.setopt(pycurl.HEADERFUNCTION, sink.header)
        c.setopt(pycurl.WRITEFUNCTION, sink.write)
        c.setopt(pycurl.NOPROGRESS, 1)
        c.setopt(pycurl.LOW_SPEED_LIMIT, LOW_SPEED_LIMIT)
        c.setopt(pycurl.LOW_SPEED_TIME, LOW_SPEED_TIME)
        _apply_common(c, token, host_is_hf=_host_is_hf(current),
                      resume_pos=sink.resume_pos)
        try:
            c.perform()
            code = c.getinfo(pycurl.RESPONSE_CODE)
        finally:
            c.close()

        if code in (301, 302, 303, 307, 308) and sink.location:
            current = urljoin(current, sink.location)
            continue
        if 200 <= code < 300:
            return
        raise RuntimeError("HTTP %s" % code)
    raise RuntimeError("превышено число редиректов")


def download_file(repo_id, revision, path, size, dest, token):
    """Скачивает один файл репозитория в dest с докачкой и повторами."""
    if size is not None and os.path.isfile(dest) and os.path.getsize(dest) == size:
        print("    [HF] ПРОПУСК (уже скачан): %s" % path)
        return

    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    part = dest + ".part"
    url = "%s/%s/resolve/%s/%s" % (
        ENDPOINT, repo_id, quote(revision, safe=""),
        "/".join(quote(seg, safe="") for seg in path.split("/")))

    last_err = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        resume_pos = os.path.getsize(part) if os.path.isfile(part) else 0
        if size is not None and resume_pos >= size:
            resume_pos = 0                 # битый .part - качаем заново
        sink = _Sink(part, resume_pos, size, path)
        try:
            _download_once(url, sink, token)
            sink.close()
            if size is not None and os.path.getsize(part) != size:
                raise RuntimeError("размер не совпал: ожидалось %s, получено %s"
                                   % (size, os.path.getsize(part)))
            if os.path.exists(dest):
                os.remove(dest)
            os.replace(part, dest)
            return
        except Exception as exc:            # noqa: BLE001 - повторяем любую сетевую ошибку
            sink.close()
            last_err = exc
            if attempt < MAX_ATTEMPTS:
                delay = min(2 ** attempt, 30)
                print("    [HF] ! %s (попытка %d/%d), повтор через %dс..."
                      % (exc, attempt, MAX_ATTEMPTS, delay))
                time.sleep(delay)

    raise RuntimeError("не удалось скачать %s: %s" % (path, last_err))


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(
        description="Скачивание репозитория HuggingFace через pycurl + HF API.")
    ap.add_argument("repo_id", help="например Linzhan/UniMate")
    ap.add_argument("local_dir", help="куда сложить файлы")
    ap.add_argument("--revision", default="main", help="ветка/тег/commit (по умолчанию main)")
    ap.add_argument("--repo-type", default="model",
                    choices=["model", "dataset", "space"])
    ap.add_argument("--include", action="append", default=[],
                    help="glob-фильтр путей для скачивания (повторяем); "
                         "без него качается весь репозиторий")
    ap.add_argument("--exclude", action="append", default=[],
                    help="glob-фильтр исключения (повторяем), сильнее --include")
    ap.add_argument("--token", default=None, help="HF-токен для приватных/gated репо")
    args = ap.parse_args()

    token = (args.token
             or os.environ.get("HF_TOKEN")
             or os.environ.get("HUGGING_FACE_HUB_TOKEN")
             or os.environ.get("HUGGINGFACE_HUB_TOKEN"))

    print("=" * 60)
    print(" [HF] pycurl downloader")
    print("   repo     : %s (%s)" % (args.repo_id, args.repo_type))
    print("   revision : %s" % args.revision)
    print("   endpoint : %s" % ENDPOINT)
    print("   dest     : %s" % args.local_dir)
    if args.include:
        print("   include  : %s" % ", ".join(args.include))
    if args.exclude:
        print("   exclude  : %s" % ", ".join(args.exclude))
    try:
        print("   libcurl  : %s" % pycurl.version)
    except Exception:
        pass
    print("=" * 60)

    try:
        files = list_repo_files(args.repo_id, args.revision, args.repo_type, token)
    except Exception as exc:               # noqa: BLE001
        sys.stderr.write("[HF] Не удалось получить список файлов: %s\n" % exc)
        return 1

    if not files:
        sys.stderr.write("[HF] В репозитории не найдено файлов.\n")
        return 1

    selected = [(p, s) for p, s in files if _wanted(p, args.include, args.exclude)]
    skipped = len(files) - len(selected)
    if not selected:
        sys.stderr.write("[HF] Ни один файл не прошёл фильтры include/exclude.\n")
        return 1

    total_bytes = sum(s for _, s in selected if s)
    print("[HF] Файлов: %d из %d (отфильтровано %d), размер: %.2f GB\n"
          % (len(selected), len(files), skipped, total_bytes / (1024 ** 3)))

    os.makedirs(args.local_dir, exist_ok=True)
    overall = tqdm(total=total_bytes, unit="B", unit_scale=True, unit_divisor=1024,
                   desc="[HF] всего", dynamic_ncols=True, file=sys.stdout)
    for idx, (path, size) in enumerate(selected, 1):
        human = "%.1f MB" % (size / (1024 ** 2)) if size else "?"
        tqdm.write("[%d/%d] %s (%s)" % (idx, len(selected), path, human))
        dest = os.path.join(args.local_dir, *path.split("/"))
        try:
            download_file(args.repo_id, args.revision, path, size, dest, token)
        except Exception as exc:           # noqa: BLE001
            overall.close()
            sys.stderr.write("[HF] ОШИБКА: %s\n" % exc)
            return 1
        if size:
            overall.update(size)
    overall.close()

    print("\n[HF] Готово: все файлы скачаны в %s" % args.local_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
