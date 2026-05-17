"""اسکریپت تست واقعی: آپلود یک فایل به Files.ir و گرفتن لینک مستقیم.

این اسکریپت یک فایل را از روی استوریج محلی به Files.ir آپلود می‌کند، سپس:

1. لینک دانلود مستقیم با احراز هویت توکن می‌سازد
2. لینک اشتراک عمومی (shareable link) ایجاد می‌کند

روش اجرا
========

اول توکنت رو یا با متغیر محیطی بده، یا توی کد همین فایل (متغیر ``FALLBACK_TOKEN``
در پایین) بنویس.

PowerShell::

    $env:FILESIR_TOKEN = "pat_xxxxxxxxxxxxxxxxxxxx"
    python examples/live_upload_and_link.py path/to/local-file.png

bash::

    export FILESIR_TOKEN=pat_xxxxxxxxxxxxxxxxxxxx
    python examples/live_upload_and_link.py /path/to/local-file.png

اگر مسیر فایل ندی، یک فایل موقت با محتوای متنی ساخته می‌شود.

می‌تونی پارامترهای دیگه هم بدی:

* ``--parent-id N``      — آپلود داخل پوشه با این ``id``
* ``--workspace-id N``   — آپلود داخل ورک‌اسپیس مشخص (پیش‌فرض ``0`` یعنی درایو شخصی)
* ``--base-url URL``     — اگر می‌خوای روی محیط دیگه‌ای تست کنی
* ``--no-public-link``   — لینک اشتراک عمومی ساخته نشود
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# روی ویندوز، stdout/stderr را به UTF-8 سوئیچ می‌کنیم تا کاراکترهای فارسی و
# ایموجی‌ها در ترمینال درست چاپ شوند.
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:  # pragma: no cover
        pass

# اجازه می‌دهیم بدون نصب پکیج هم کار کند: src/ را به sys.path اضافه می‌کنیم.
_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from filesir import FilesIrClient  # noqa: E402
from filesir.exceptions import FilesIrError  # noqa: E402

# ---------------------------------------------------------------------------
# اگر نمی‌خوای متغیر محیطی استفاده کنی، توکنت رو همینجا بذار.
# ولی هرگز این مقدار را در گیت کامیت نکن.
FALLBACK_TOKEN: str = ""
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = "https://my.files.ir/api/v1"


def _human_size(n: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    f = float(n)
    i = 0
    while f >= 1024 and i < len(units) - 1:
        f /= 1024
        i += 1
    return f"{f:.2f} {units[i]}"


def _make_temp_file() -> str:
    fd, path = tempfile.mkstemp(prefix="filesir-test-", suffix=".txt")
    os.close(fd)
    body = (
        "filesir-async-client live test\n"
        f"timestamp: {datetime.utcnow().isoformat()}Z\n"
        + ("ping " * 200)
    )
    Path(path).write_text(body, encoding="utf-8")
    return path


async def run(
    *,
    token: str,
    base_url: str,
    file_path: str,
    parent_id: int | None,
    workspace_id: int | None,
    create_public_link: bool,
) -> int:
    print(f"== filesir-async-client live test ==")
    print(f"base_url       : {base_url}")
    print(f"file           : {file_path}")
    print(f"parent_id      : {parent_id}")
    print(f"workspace_id   : {workspace_id}")
    print()

    if not os.path.isfile(file_path):
        print(f"❌ مسیر فایل معتبر نیست: {file_path}")
        return 2

    size = os.path.getsize(file_path)
    print(f"اندازه فایل    : {_human_size(size)} ({size:,} bytes)")
    print()

    async with FilesIrClient(access_token=token, base_url=base_url) as client:
        # --- 1. وضعیت فضای ذخیره‌سازی -----------------------------------------
        try:
            usage = await client.storage.space_usage()
            print("== فضای ذخیره‌سازی ==")
            print(f"  used      : {_human_size(usage.used)}")
            print(
                "  available : "
                + (
                    _human_size(usage.available)
                    if usage.available is not None
                    else "نامحدود"
                ),
            )
            print(
                "  remaining : "
                + (
                    _human_size(usage.remaining)
                    if usage.remaining is not None
                    else "نامحدود"
                ),
            )
            print()
        except FilesIrError as e:
            print(f"⚠️  خواندن space_usage شکست خورد: {e}")
            print()

        # --- 2. آپلود فایل ----------------------------------------------------
        print("== آپلود ==")
        last_pct = -1

        def progress(done: int, total: int) -> None:
            nonlocal last_pct
            pct = int(done * 100 / total) if total > 0 else 100
            if pct != last_pct:
                last_pct = pct
                print(
                    f"\r  پیشرفت: {pct:3d}%  "
                    f"({_human_size(done)}/{_human_size(total)})",
                    end="",
                    flush=True,
                )

        try:
            entry = await client.uploads.upload_file(
                file_path,
                parent_id=parent_id,
                workspace_id=workspace_id,
                progress=progress,
            )
        except FilesIrError as e:
            print()
            print(f"❌ آپلود شکست خورد: {e}")
            return 3
        print()  # خط جدید بعد از progress
        print(f"  ✅ آپلود انجام شد")
        print(f"     id       : {entry.id}")
        print(f"     name     : {entry.name}")
        print(f"     mime     : {entry.mime}")
        print(f"     size     : {_human_size(entry.file_size or 0)}")
        print(f"     hash     : {entry.hash}")
        print()

        # --- 3. لینک دانلود مستقیم با توکن -----------------------------------
        print("== لینک دانلود مستقیم (با توکن) ==")
        direct = client.files.direct_download_url(entry.id)
        print(f"  {direct}")
        print()
        print("  این لینک در مرورگر / curl / wget قابل استفاده‌ست بدون هدر Authorization.")
        print()

        # --- 4. لینک اشتراک عمومی (shareable link) ---------------------------
        if create_public_link:
            print("== ساخت لینک اشتراک عمومی ==")
            try:
                link = await client.links.create(
                    entry.id,
                    allow_download=True,
                )
                print(f"  ✅ ساخته شد")
                print(f"     id    : {link.id}")
                print(f"     hash  : {link.hash}")
                if link.hash:
                    # الگوی URL مشتق شده، چون swagger خود مسیر public را اعلام نمی‌کند.
                    print(f"     URL   : https://files.ir/drive/s/{link.hash}")
                print()
            except FilesIrError as e:
                print(f"  ⚠️  ساخت لینک اشتراک شکست خورد: {e}")
                print()

        print("== پایان تست ==")
        return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="آپلود واقعی به Files.ir و گرفتن لینک مستقیم برای تست.",
    )
    p.add_argument(
        "file",
        nargs="?",
        help="مسیر فایل محلی برای آپلود. اگر ندی، فایل موقت ساخته می‌شود.",
    )
    p.add_argument(
        "--token",
        default=os.environ.get("FILESIR_TOKEN", FALLBACK_TOKEN),
        help="توکن دسترسی. می‌تونی از env با FILESIR_TOKEN هم بدی.",
    )
    p.add_argument(
        "--base-url",
        default=os.environ.get("FILESIR_BASE_URL", DEFAULT_BASE_URL),
        help="آدرس پایه API.",
    )
    p.add_argument("--parent-id", type=int, default=None,
                   help="id پوشه‌ی والد. پیش‌فرض: ریشه.")
    p.add_argument("--workspace-id", type=int, default=None,
                   help="id ورک‌اسپیس. ۰ یعنی درایو شخصی.")
    p.add_argument("--no-public-link", action="store_true",
                   help="لینک اشتراک عمومی ساخته نشود.")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    token = (args.token or "").strip()
    if not token:
        print(
            "❌ توکن داده نشده. یکی از این دو راه را انتخاب کن:\n"
            "   1) متغیر محیطی FILESIR_TOKEN را تنظیم کن.\n"
            "   2) یا داخل examples/live_upload_and_link.py مقدار "
            "FALLBACK_TOKEN را پر کن.",
            file=sys.stderr,
        )
        return 1

    file_path = args.file or _make_temp_file()
    return asyncio.run(
        run(
            token=token,
            base_url=args.base_url,
            file_path=file_path,
            parent_id=args.parent_id,
            workspace_id=args.workspace_id,
            create_public_link=not args.no_public_link,
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
