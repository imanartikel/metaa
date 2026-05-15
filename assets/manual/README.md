# Manual Ad Images

Taruh gambar manual untuk iklan di folder ini.

File gambar di folder ini tidak ikut Git commit.

Rekomendasi naming:

```text
draft_20260515_bengkel_wl_01.jpg
draft_20260515_bengkel_wl_02.png
produk_offer_audience_variant.jpg
```

Format aman untuk Meta:

```text
.jpg
.jpeg
.png
```

Flow:

```text
1. Buat draft via Telegram /draft
2. Taruh gambar manual di assets/manual/
3. Attach gambar ke draft:
   /attach_image draft_id | filename.jpg
4. Preview:
   /preview draft_id
5. Push:
   /push_draft draft_id
```
