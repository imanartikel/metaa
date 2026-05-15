# Meta Ad Drafter

Local Python app untuk bikin draft Meta Ads dengan bantuan AI secara aman.

Status project saat ini:

- connect ke Meta Marketing API
- validasi token dan identity
- baca ad account dan Page
- upload image creative
- create Ad Creative object
- create campaign, ad set, dan ad dalam status `PAUSED`
- generate draft JSON + placeholder image lokal
- trigger draft awal via Telegram bot lokal

Belum ada auto publish. Belum ada iklan `ACTIVE`. Belum ada spend otomatis.

## Safety Rules

Project ini wajib menjaga aturan berikut:

```text
campaign status = PAUSED
ad set status  = PAUSED
ad status      = PAUSED
```

AI dan Telegram boleh membantu bikin draft, copy, image prompt, image asset, dan object iklan. Publish tetap manual dari Ads Manager.

## Repo

```text
https://github.com/imanartikel/metaa
```

## Restore di Mesin Baru

### macOS / Linux

```bash
git clone https://github.com/imanartikel/metaa.git
cd metaa
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`, isi credential asli.

### Windows PowerShell

```powershell
git clone https://github.com/imanartikel/metaa.git
cd metaa
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env`, isi credential asli.

Kalau PowerShell menolak activate script:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## Environment Variables

Isi `.env` lokal. Jangan commit file ini.

```text
META_ACCESS_TOKEN=
META_AD_ACCOUNT_ID=
META_PAGE_ID=
META_APP_ID=
META_APP_SECRET=
META_GRAPH_API_VERSION=v25.0

TELEGRAM_BOT_TOKEN=
TELEGRAM_ALLOWED_USER_IDS=
TELEGRAM_VERIFY_SSL=true

ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-haiku-4-5-20251001
ANTHROPIC_VERIFY_SSL=true
```

Catatan:

- `META_ACCESS_TOKEN`: token Meta yang punya `ads_management`.
- `META_AD_ACCOUNT_ID`: boleh angka saja, contoh `927494890169245`.
- `META_PAGE_ID`: Page ID yang muncul dari `python src/main.py test`.
- `META_APP_ID` dan `META_APP_SECRET`: dipakai untuk `/debug_token`.
- `TELEGRAM_ALLOWED_USER_IDS`: isi user id Telegram yang boleh pakai bot.
- `TELEGRAM_VERIFY_SSL=false`: hanya untuk development kalau Python lokal gagal SSL ke Telegram.
- `ANTHROPIC_API_KEY`: API key Claude. Kalau kosong, draft tetap jalan pakai placeholder.
- `ANTHROPIC_MODEL`: default murah/cepat `claude-haiku-4-5-20251001`.
- `ANTHROPIC_VERIFY_SSL=false`: hanya untuk development kalau Python lokal gagal SSL ke Anthropic.

## Struktur Folder

```text
meta-ad-drafter/
  .env.example
  requirements.txt
  README.md
  docs/
    privacy-policy.html
  input/
    brief.example.json
  assets/
    test.jpg
    manual/
      README.md
  output/
    logs/
  src/
    main.py
    config.py
    meta_api.py
    draft_package.py
    create_creative.py
    create_paused_draft.py
    telegram_bot.py
    test_connection.py
    upload_image.py
```

Runtime files seperti `.env`, logs, generated drafts, generated images, dan manual images di-ignore oleh Git.

## Quick Health Check

```bash
python src/main.py test
python src/main.py whoami
python src/main.py check-account
```

Expected:

- token valid
- Page kebaca
- ad account reachable

## Flow Manual Aman

### 1. Generate draft lokal

```bash
python src/main.py draft-package --brief input/brief.example.json
```

Kalau `ANTHROPIC_API_KEY` terisi, command ini otomatis pakai Claude Haiku untuk copywriting. Untuk paksa placeholder:

```bash
python src/main.py draft-package --brief input/brief.example.json --no-ai
```

Output:

```text
output/drafts/draft_*.json
assets/generated/draft_*.jpg
```

### 2. Review payload creative tanpa write ke Meta

```bash
python src/main.py create-creative-from-draft output/drafts/draft_xxx.json --dry-run
```

### 3. Upload image + create Ad Creative

```bash
python src/main.py create-creative-from-draft output/drafts/draft_xxx.json
```

Output penting:

```text
creative_id: ...
image_hash: ...
```

### 4. Create campaign/ad set/ad dalam status PAUSED

```bash
python src/main.py create-paused-draft-ad \
  --creative-id 1496767121939472 \
  --campaign-name "AI Draft - Placeholder Campaign" \
  --adset-name "AI Draft - Placeholder Ad Set" \
  --ad-name "AI Draft - Placeholder Ad" \
  --daily-budget 50000 \
  --country ID
```

Semua object dibuat `PAUSED`.

Untuk dry run:

```bash
python src/main.py create-paused-draft-ad --creative-id 1496767121939472 --dry-run
```

## Windows PowerShell Line Continuation

Di PowerShell, pakai backtick:

```powershell
python src/main.py create-paused-draft-ad `
  --creative-id 1496767121939472 `
  --campaign-name "AI Draft - Placeholder Campaign" `
  --adset-name "AI Draft - Placeholder Ad Set" `
  --ad-name "AI Draft - Placeholder Ad" `
  --daily-budget 50000 `
  --country ID
```

Di macOS/Linux, pakai backslash:

```bash
python src/main.py create-paused-draft-ad \
  --creative-id 1496767121939472 \
  --campaign-name "AI Draft - Placeholder Campaign" \
  --adset-name "AI Draft - Placeholder Ad Set" \
  --ad-name "AI Draft - Placeholder Ad" \
  --daily-budget 50000 \
  --country ID
```

## Telegram Bot Lokal

Telegram sekarang hanya bikin draft lokal. Bot belum auto upload ke Meta.

### Cek bot token

```bash
python src/main.py telegram-whoami
```

### Cari user id

1. Kirim `/start` ke bot.
2. Jalankan:

```bash
python src/main.py telegram-updates
```

Isi `.env`:

```text
TELEGRAM_ALLOWED_USER_IDS=208131918
```

### Jalankan bot

```bash
python src/main.py telegram-bot
```

Command Telegram:

```text
/id
/draft product | offer | audience | landing_url | budget | gender
/list_drafts
/preview d1
/attach_image d1 | filename.jpg
/push_draft d1
```

Contoh:

```text
/draft Bengkel Mobil WL | Gratis cek kaki-kaki | Pemilik mobil Jakarta | https://example.com | 75000 | all
/list_drafts
/preview d1
/attach_image d1 | bengkel_wl_01.jpg
/push_draft d1
```

Bot akan membuat:

```text
input/telegram/*_brief.json
output/drafts/draft_*.json
assets/generated/draft_*.jpg
```

Kalau `ANTHROPIC_API_KEY` ada di `.env`, Telegram `/draft` akan pakai Claude Haiku untuk copy dan creative direction. Kalau key kosong atau API error, bot fallback ke placeholder.

`/push_draft` akan upload image, create creative, lalu create campaign/ad set/ad dalam status `PAUSED`. Command ini tidak pernah publish `ACTIVE`.

## Manual Images

Gambar iklan manual ditaruh di:

```text
assets/manual/
```

File gambar di folder ini tidak ikut Git. Pakai command Telegram:

```text
/attach_image d1 | filename.jpg
```

Contoh:

```text
/attach_image d1 | bengkel_wl_01.jpg
```

Setelah attach, `/push_draft` akan upload gambar manual itu ke Meta.

Default targeting Telegram:

```text
region: Jawa + Bali
age: 25-65
gender: all
```

Gender bisa diisi:

```text
all
pria
wanita
```

## Meta App Privacy Policy

Template tersedia:

```text
docs/privacy-policy.html
```

Untuk Meta Developer, privacy policy harus public. Bisa pakai:

- Google Docs public link
- Google Sites
- GitHub Pages
- Netlify/Vercel
- hosting sendiri

## Important IDs dari Test Terakhir

Contoh IDs yang pernah berhasil dibuat:

```text
creative_id: 1496767121939472
campaign_id: 120245030770110050
adset_id: 120245030770880050
ad_id: 120245030771690050
```

Ini hanya referensi. Untuk draft baru, pakai ID terbaru dari output command.

## Troubleshooting

### Missing `META_ACCESS_TOKEN`

Isi `.env`.

### Token valid tapi upload image gagal

Pastikan identity token punya:

```text
ads_management
write access / Manage campaigns
access ke ad account
```

Cek identity token:

```bash
python src/main.py whoami
```

### `Facebook Page is missing`

`META_PAGE_ID` salah atau token tidak punya akses ke Page itu.

Jalankan:

```bash
python src/main.py test
```

Pakai Page ID yang muncul di output.

### `app is in development mode`

Meta App harus Live/Public untuk create ad creative.

### Telegram tidak balas

Pastikan bot polling jalan:

```bash
python src/main.py telegram-bot
```

Cek update:

```bash
python src/main.py telegram-updates
```

Cek log:

```text
output/logs/telegram-bot.err.log
output/logs/telegram-bot.out.log
```

### Python SSL error ke Telegram

Untuk development lokal, set:

```text
TELEGRAM_VERIFY_SSL=false
```

Untuk production, sebaiknya balik ke:

```text
TELEGRAM_VERIFY_SSL=true
```

## Next Roadmap

- Vertex/Gemini image provider
- campaign config JSON
- Telegram `/push_draft` yang tetap create semua object dalam status `PAUSED`
- manual review summary sebelum publish
