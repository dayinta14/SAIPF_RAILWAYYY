SAIPF FRONTEND FIX 404
======================

PENTING:
1. Ekstrak ZIP sampai menjadi folder biasa.
2. Jangan menjalankan file BAT langsung dari tampilan isi ZIP.
3. Jalankan backend dengan START_BACKEND_FIX_TESSERACT.bat.
4. Pastikan http://127.0.0.1:8000/docs dapat dibuka.
5. Klik dua kali BUKA_FRONTEND_FIX_404.bat.
6. Frontend akan terbuka di http://127.0.0.1:5510/index.html.

Port frontend diubah dari 5500 ke 5510 untuk menghindari bentrok dengan server lama yang menyebabkan 404.

Susunan folder wajib:
SAIPF_Frontend_FIX_404
|- index.html
|- css\style.css
|- js\app.js
|- frontend_server.py
|- JALANKAN_SERVER_FRONTEND.bat
|- BUKA_FRONTEND_FIX_404.bat
