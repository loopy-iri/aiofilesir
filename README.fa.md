# filesir-async-client

<div dir="rtl">

کتابخانه‌ی async پایتون ۳.۱۰+ برای [Files.ir](https://files.ir).

این کتابخانه روی `httpx.AsyncClient` و `pydantic` v2 ساخته شده. تمام اندپوینت‌های
موجود در `swagger.yaml` رو با کوروتین‌های type-hinted پوشش می‌ده، توکن `Bearer` رو
خودکار توی هدر می‌فرسته، شکست‌های موقتی (5xx، 429، خطای شبکه) رو با backoff
نمایی دوباره تلاش می‌کنه، و آپلود فایل‌های بزرگ رو با تشخیص خودکار
`uploadMode` (single / s3-single / s3-multipart / tus) انجام می‌ده.

---

## نصب

</div>

از PyPI (وقتی منتشر شد):

```bash
pip install filesir-async-client
```

مستقیم از Git (فعلاً پیشنهاد می‌شود):

```bash
pip install "git+https://github.com/loopy-iri/aiofilesir.git"
```

پین کردن به تگ یا شاخه:

```bash
pip install "git+https://github.com/loopy-iri/aiofilesir.git@v0.1.0"
pip install "git+https://github.com/loopy-iri/aiofilesir.git@main"
```

اضافه به `requirements.txt`:

```
filesir-async-client @ git+https://github.com/loopy-iri/aiofilesir.git@main
```

<div dir="rtl">

اگر از سورس استفاده می‌کنی (همین ریپو):

</div>

```bash
pip install -e .[dev]
```

<div dir="rtl">

> **نکته**: نیازی به نصب نیست تا تست‌ها اجرا شوند؛ فایل `conftest.py` در ریشه‌ی
> پروژه پوشه‌ی `src/` را به `sys.path` اضافه می‌کند.

---

## شروع سریع

</div>

```python
import asyncio
from filesir import FilesIrClient


async def main() -> None:
    async with FilesIrClient(access_token="pat_...") as client:
        # وضعیت فضای ذخیره‌سازی
        usage = await client.storage.space_usage()
        print(usage.used, usage.available, usage.remaining)

        # ساخت پوشه
        folder = await client.folders.create(name="reports")

        # آپلود فایل (به‌طور خودکار بهترین استراتژی را انتخاب می‌کند)
        entry = await client.uploads.upload_file(
            "/tmp/big-video.mp4",
            parent_id=folder.id,
            progress=lambda done, total: print(f"{done}/{total}"),
        )

        # ساخت لینک مستقیم برای دانلود (شامل توکن در query string)
        url = client.files.direct_download_url(entry.id)
        print("Direct download URL:", url)

        # دانلود استریمی روی دیسک
        await client.files.download_to_file(entry.id, "/tmp/copy.mp4")


asyncio.run(main())
```

<div dir="rtl">

---

## احراز هویت

</div>

```python
# با توکن شخصی موجود (account settings > developers)
client = FilesIrClient(access_token="pat_...")

# یا با ایمیل/رمز و گرفتن خودکار توکن
client = await FilesIrClient.from_credentials(
    email="me@example.com",
    password="secret",
    token_name="my-script",
)
```

<div dir="rtl">

---

## منابع موجود

| Resource | اندپوینت‌ها | توضیح کوتاه |
|----------|--------------|---------|
| `client.auth` | `/auth/register`, `/auth/login` | ثبت‌نام و ورود |
| `client.storage` | `/user/space-usage` | فضای استفاده‌شده و باقی‌مانده |
| `client.files` | `/drive/file-entries`, `/file-entries/{id}`, `/move`, `/duplicate`, `/restore`, `/delete` | لیست/به‌روزرسانی/جابجایی/کپی/حذف/دانلود |
| `client.folders` | `/folders` | ساخت پوشه |
| `client.uploads` | `/uploads`, `/uploads-new/*` | آپلود ساده + سشن‌بیس + استراتژی‌های s3-single / s3-multipart / tus |
| `client.sharing` | `/file-entries/{id}/share|change-permissions|unshare` | اشتراک با کاربران دیگر |
| `client.starring` | `/file-entries/star|unstar` | ستاره‌دار کردن |
| `client.links` | `/file-entries/{id}/shareable-link`, `/file_entries/{id}/shareable-link` | لینک‌های اشتراک عمومی |
| `client.workspaces` | `/me/workspaces`, `/workspace/*`, `/workspaces/{id}/activity-logs` | ورک‌اسپیس‌ها، عضوها، دعوت‌نامه‌ها |
| `client.tags` | `/taggable/*` | تگ‌گذاری |

---

## آپلود فایل‌های بزرگ

`upload_file(...)` ابتدا `/uploads-new/init` را صدا می‌زند و بسته به `uploadMode` که سرور برمی‌گرداند، یکی از این استراتژی‌ها را انتخاب می‌کند:

* **`single`** — فایل کامل با یک درخواست به Files.ir فرستاده می‌شود.
* **`s3-single`** — یک `PUT` مستقیم به URL امضاشده‌ی S3، سپس فراخوانی `complete`.
* **`s3-multipart`** — فایل به قطعاتی به اندازه‌ی `partSize` تقسیم می‌شود، URL‌های هر قطعه از سرور گرفته می‌شود، قطعات با کنترل همزمانی موازی روی S3 آپلود می‌شوند، و در پایان `ETag` همه‌ی قطعات به `complete` فرستاده می‌شود.
* **`tus`** — آپلود قابل ازسرگیری با پروتکل TUS (در داخل کتابخانه پیاده شده، نیازی به وابستگی خارجی نیست).

اگر در حین آپلود خطایی رخ بده، سشن سمت سرور به‌صورت best-effort با `DELETE /uploads-new/{sid}` لغو می‌شود.

</div>

```python
# آپلود از مسیر دیسک
entry = await client.uploads.upload_file("/path/to/big.mp4")

# آپلود از بایت
entry = await client.uploads.upload_file(
    b"hello world",
    filename="hello.txt",
    parent_id=42,
    workspace_id=0,
)

# با پیشرفت
async def on_progress(done: int, total: int) -> None:
    pct = int(done * 100 / total) if total else 100
    print(f"{pct}%  ({done}/{total})")

entry = await client.uploads.upload_file(
    "/path/to/big.mp4",
    progress=on_progress,
)
```

<div dir="rtl">

---

## لینک دانلود مستقیم

`direct_download_url(entry_id)` یک URL آماده می‌دهد که می‌تواند مستقیم در مرورگر، `curl`، `wget` یا `<a href="...">` استفاده شود — بدون نیاز به هدر `Authorization`.

</div>

```python
async with FilesIrClient(access_token="pat_...") as client:
    url = client.files.direct_download_url(entry_id=42)
    # https://my.files.ir/api/v1/file-entries/42?accessToken=pat_...

    # برای thumbnail
    url_thumb = client.files.direct_download_url(42, thumbnail=True)

    # بدون توکن (برای لینک‌های preview)
    public = client.files.direct_download_url(
        42, access_token="", preview_token="...",
    )
```

<div dir="rtl">

---

## مدیریت خطا

تمام خطاهای کتابخانه از کلاس پایه `FilesIrError` مشتق می‌شوند:

</div>

```python
from filesir.exceptions import (
    FilesIrError,           # پایه
    NetworkError,           # خطای شبکه پس از تمام شدن retry
    AuthenticationError,    # 401
    ForbiddenError,         # 403
    NotFoundError,          # 404
    ValidationError,        # 422 (شامل dict خطاهای فیلدها)
    RateLimitError,         # 429 (شامل retry_after به ثانیه)
    ServerError,            # 5xx
    UploadError,            # خطای جریان آپلود
)

try:
    await client.files.list()
except ValidationError as e:
    print(e.message, e.errors)
except FilesIrError as e:
    print("API error:", e)
```

<div dir="rtl">

---

## سیاست retry

به‌صورت پیش‌فرض ۳ تلاش با backoff نمایی (شروع از 0.5 ثانیه، سقف 30 ثانیه)
برای خطاهای شبکه، 5xx و 429 انجام می‌شود. هدر `Retry-After` رعایت می‌شود.

</div>

```python
from filesir import FilesIrClient, RetryPolicy

policy = RetryPolicy(
    max_attempts=5,
    initial_backoff=1.0,
    max_backoff=60.0,
    backoff_multiplier=2.0,
    backoff_jitter=0.2,
)
client = FilesIrClient(access_token="...", retry=policy)
```

<div dir="rtl">

---

## امنیت

* توکن فقط در حافظه‌ی کلاینت نگهداری می‌شود.
* فیلتر `AuthorizationRedactor` روی لاگر `filesir` نصب می‌شود تا توکن هرگز در لاگ‌ها ظاهر نشود.
* در `external_put` (آپلود قطعات S3 و TUS) هدر `Authorization` به URL خارجی فرستاده **نمی‌شود**.

---

## اجرای تست‌ها

</div>

```bash
python -m pytest
```

<div dir="rtl">

شامل:
* تست‌های unit برای transport، retry، redactor، مدل‌ها، pagination
* تست‌های شکل-سیمی هر منبع با `httpx.MockTransport`
* تست‌های property-based با Hypothesis برای ریاضیات chunking در multipart

---

## تست واقعی روی Files.ir

اسکریپت `examples/live_upload_and_link.py` یک فایل را روی Files.ir آپلود می‌کند، لینک مستقیم می‌گیرد و لینک اشتراک عمومی می‌سازد:

</div>

```powershell
$env:FILESIR_TOKEN = "pat_xxxxxxxxxxxx"
python examples/live_upload_and_link.py path/to/local-file.png
```

```bash
export FILESIR_TOKEN=pat_xxxxxxxxxxxx
python examples/live_upload_and_link.py /path/to/local-file.png
```

<div dir="rtl">

اگر فایل ندهی، یک فایل متنی موقت ساخته می‌شود.

پارامترهای دیگر:

* `--parent-id N` — آپلود داخل پوشه‌ی مشخص
* `--workspace-id N` — آپلود در ورک‌اسپیس مشخص (`0` = درایو شخصی)
* `--base-url URL` — تغییر آدرس پایه برای محیط تست
* `--no-public-link` — ساخته نشدن لینک اشتراک عمومی

---

## مجوز

MIT.

</div>
