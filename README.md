# Meta Ad Drafter

Aplikasi Python lokal untuk fondasi sistem AI-assisted Meta Ads Drafting.

Fase ini hanya membuat layer koneksi ke Meta Marketing API:

- validasi credential/token
- membaca daftar ad account
- membaca daftar Page
- upload image creative dan mengambil `image_hash`
- menyimpan response API yang sudah disensor ke `output/logs/`

Belum ada fitur AI generation, landing page generation, optimization, atau pembuatan campaign/adset/ad.

## Prinsip Safety

Aplikasi ini tidak pernah membuat iklan dengan status `ACTIVE` dan tidak pernah menjalankan spending otomatis.

Untuk pengembangan berikutnya, semua pembuatan campaign, ad set, dan ad wajib default ke:

```text
PAUSED
```

Di kode sudah ada helper `require_paused_status()` untuk menolak status `ACTIVE`.

## Privacy Policy untuk Meta App

Meta Developer biasanya meminta URL privacy policy public saat app dipublish. Template sudah tersedia di:

```text
docs/privacy-policy.html
```

Upload file itu ke hosting public seperti GitHub Pages, Netlify, Vercel, Google Sites, atau hosting domain sendiri. Setelah public, masukkan URL-nya ke bagian Privacy Policy URL di Meta Developer.

Sebelum dipakai, ganti email di bagian `Contact` dari:

```text
your-email@example.com
```

menjadi email aktif milik kamu/bisnis.

## Struktur Folder

```text
meta-ad-drafter/
  .env
  .env.example
  requirements.txt
  src/
    main.py
    config.py
    meta_api.py
    test_connection.py
    upload_image.py
  assets/
  output/
    logs/
```

Penjelasan singkat:

- `.env`: credential lokal. Jangan commit file ini.
- `.env.example`: contoh format environment variable.
- `src/config.py`: loader konfigurasi dan logging.
- `src/meta_api.py`: helper class untuk raw Meta Graph API.
- `src/main.py`: entrypoint CLI.
- `src/test_connection.py`: command untuk tes token, ad account, dan Page.
- `src/upload_image.py`: command upload image ke `/act_<AD_ACCOUNT_ID>/adimages`.
- `assets/`: tempat simpan file gambar lokal, misalnya `test.jpg`.
- `output/logs/`: tempat menyimpan log dan response API.

## Setup

Masuk ke folder project:

```powershell
cd "c:\Users\62812\Desktop\fb ad\meta-ad-drafter"
```

Buat virtual environment Python 3.12:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install dependency:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Isi file `.env`:

```text
META_ACCESS_TOKEN=
META_AD_ACCOUNT_ID=
META_PAGE_ID=
META_APP_ID=
META_APP_SECRET=
META_GRAPH_API_VERSION=v25.0
```

Catatan:

- `META_ACCESS_TOKEN`: access token dari Meta.
- `META_AD_ACCOUNT_ID`: isi angka saja boleh, contoh `1234567890`; kode akan otomatis memakai format `act_1234567890`.
- `META_PAGE_ID`: Page ID untuk kebutuhan future creative/ad flow.
- `META_APP_ID` dan `META_APP_SECRET`: dipakai untuk validasi token via `/debug_token`.
- `META_GRAPH_API_VERSION`: versi Graph API eksplisit. Default saat ini diset ke `v25.0`.

## Cara Menjalankan

Tes koneksi:

```powershell
python src/main.py test
```

Cek identitas user/system user dari token:

```powershell
python src/main.py whoami
```

Cek ad account yang ada di `.env` secara langsung:

```powershell
python src/main.py check-account
```

Upload gambar:

```powershell
python src/main.py upload-image assets/test.jpg
```

Buat image ad creative dari `image_hash` yang sudah ada:

```powershell
python src/main.py create-creative `
  --image-hash ac0a279661be2f49b99c8022bb6c69dd `
  --name "WL 629 - Test Creative 001" `
  --link-url "https://example.com" `
  --message "Primary text iklan ditulis di sini." `
  --headline "Headline iklan" `
  --description "Deskripsi singkat opsional." `
  --cta LEARN_MORE
```

Upload image lalu langsung buat creative:

```powershell
python src/main.py create-creative `
  --image-path assets/test.jpg `
  --name "WL 629 - Test Creative 002" `
  --link-url "https://example.com" `
  --message "Primary text iklan ditulis di sini." `
  --headline "Headline iklan" `
  --cta LEARN_MORE
```

Cek payload tanpa kirim write request ke Meta:

```powershell
python src/main.py create-creative `
  --image-hash ac0a279661be2f49b99c8022bb6c69dd `
  --name "Dry Run Creative" `
  --link-url "https://example.com" `
  --message "Primary text iklan ditulis di sini." `
  --headline "Headline iklan" `
  --dry-run
```

Buat draft package dari brief JSON dan placeholder image lokal:

```powershell
python src/main.py draft-package --brief input/brief.example.json
```

Hasilnya:

```text
output/drafts/draft_*.json
assets/generated/draft_*.jpg
```

Cek payload creative dari draft tanpa upload/create ke Meta:

```powershell
python src/main.py create-creative-from-draft output/drafts/draft_YYYYMMDDTHHMMSSZ_bengkel_mobil_wl.json --dry-run
```

Kalau draft sudah oke, upload image dan buat creative object:

```powershell
python src/main.py create-creative-from-draft output/drafts/draft_YYYYMMDDTHHMMSSZ_bengkel_mobil_wl.json
```

Mode verbose kalau butuh debug log di terminal:

```powershell
python src/main.py --verbose test
```

## Contoh Output

Contoh output `test`:

```text
Meta Ads Drafter connection test
--------------------------------

Token
  status: valid
  app_id: 123456789
  expires_at: 1760000000
  scopes: 8 scope(s)

Ad accounts
  count: 1
  1. Nama Ad Account | act_123456789 | 1

Pages
  count: 1
  1. Nama Page | 123456789 | Business

[OK] Connection test completed.
API responses saved in: C:\...\meta-ad-drafter\output\logs
```

Contoh output `upload-image`:

```text
Meta Ads Drafter image upload
-----------------------------
image: C:\...\meta-ad-drafter\assets\test.jpg
ad_account: 123456789
status: uploading

[OK] Image uploaded.
image_hash: abcdef1234567890abcdef1234567890
response_log: C:\...\meta-ad-drafter\output\logs\20260514T...\_POST_200_act_123456789_adimages.json
```

Contoh output `create-creative`:

```text
Meta Ads Drafter image creative
--------------------------------
ad_account: 123456789
page_id: 123456789
name: WL 629 - Test Creative 001

[OK] Image ad creative created.
creative_id: 123456789012345
image_hash: ac0a279661be2f49b99c8022bb6c69dd
creative_response_log: C:\...\output\logs\20260514T...\_POST_200_act_123456789_adcreatives.json
creative_artifact: C:\...\output\creative_123456789012345.json
```

## Troubleshooting

`[CONFIG ERROR] Missing required environment variable: META_ACCESS_TOKEN`

Artinya `.env` belum diisi atau token masih kosong.

`[META API ERROR] Error validating access token`

Biasanya token expired, salah copy, atau permission kurang.

Tidak ada ad account yang muncul:

- pastikan user/system user punya akses ke ad account
- pastikan token punya permission yang sesuai
- jalankan `python src/main.py whoami` dan cocokkan nama token dengan user/system user yang diberi akses di Business Manager
- cek Business Manager access

Upload image gagal:

- pastikan file benar-benar ada, misalnya `assets/test.jpg`
- pastikan `META_AD_ACCOUNT_ID` benar
- pastikan token punya akses ke ad account tersebut
- pastikan user/system user punya role `Advertiser` atau lebih tinggi di ad account
- pastikan token punya permission `ads_management`
- cek file JSON terbaru di `output/logs/`

Create creative gagal dengan pesan `Facebook Page is missing`:

- pastikan `META_PAGE_ID` adalah Page yang benar-benar kebaca dari `python src/main.py test`
- Page ID harus milik Page yang token/app bisa akses

Create creative gagal dengan pesan `Ads creative post was created by an app that is in development mode`:

- image upload sudah berhasil, tetapi app Meta masih dalam Development Mode
- ubah app `ad drafter` ke Live/Public Mode di Meta Developer
- pastikan permission iklan yang dipakai app sudah siap untuk mode live
- setelah app live, jalankan ulang `python src/main.py create-creative-from-draft ...`

Response API selalu disimpan di:

```text
output/logs/
```

Token dan secret disensor otomatis di log dengan nilai:

```text
***REDACTED***
```
