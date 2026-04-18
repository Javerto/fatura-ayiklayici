@echo off
chcp 65001 >nul
echo ============================================
echo   Fatura Ayiklayici - EXE Derleme
echo ============================================
echo.

echo [1/6] Uygulama ikonu olusturuluyor...
if exist "icon.ico" del "icon.ico"
python -c "import struct, base64; png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAAAWElEQVR42mNgGAWDFeiHTPtPLh51wIA7YMGuF/8H3AEUO4IaDqDIEdRyANmOoMQBVEmYow5A1gwEd/Dh0SgYTQPEpI3RKBhNA6NRMOqAUQeMOmC0r4kLAAAnW4FDe82NqwAAAABJRU5ErkJggg=='); ico = struct.pack('<HHH', 0, 1, 1); ico += struct.pack('<BBBBHHII', 32, 32, 0, 0, 1, 32, len(png), 22); ico += png; open('icon.ico', 'wb').write(ico); print('icon.ico olusturuldu.')"
if not exist "icon.ico" (
    echo HATA: Ikon olusturulamadi!
    pause & exit /b 1
)

echo [2/6] Temiz sanal ortam olusturuluyor...
if exist ".venv_build" rmdir /s /q ".venv_build"
python -m venv .venv_build
if errorlevel 1 (
    echo HATA: Sanal ortam olusturulamadi.
    pause & exit /b 1
)

echo [3/6] Sadece gerekli kutuphaneler kuruluyor...
.venv_build\Scripts\pip install --quiet google-genai pymupdf python-dotenv openpyxl pyinstaller
if errorlevel 1 (
    echo HATA: Kutuphane kurulumu basarisiz.
    pause & exit /b 1
)

echo [4/6] EXE olusturuluyor...
.venv_build\Scripts\pyinstaller ^
    --onefile ^
    --windowed ^
    --name "FaturaAyiklayici" ^
    --icon icon.ico ^
    --collect-all google.genai ^
    --hidden-import fitz ^
    --hidden-import openpyxl ^
    --hidden-import dotenv ^
    main.py

echo [5/6] Temizlik yapiliyor...
if exist ".venv_build" rmdir /s /q ".venv_build"
if exist "build" rmdir /s /q "build"
rem icon.ico ve spec dosyasi silinmiyor (pyinstaller icon.ico'ya ihtiyac duyuyor)

echo.
if exist "dist\FaturaAyiklayici.exe" (
    echo BASARILI!
    echo.
    echo Dagitim dosyasi: dist\FaturaAyiklayici.exe
    for %%A in ("dist\FaturaAyiklayici.exe") do echo Boyut: %%~zA bayt
    echo.
    echo Bu EXE dosyasini ekip arkadaslarinizla paylasabilirsiniz.
    echo Ilk acilista API key girilmesi gerekecektir.
) else (
    echo HATA: EXE olusturulamadi. Yukaridaki hata mesajini inceleyin.
)
echo.
pause
