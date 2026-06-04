@echo off
REM ============================================================
REM  Build del ejecutable Smart Manager AI (Windows)
REM ============================================================
echo [1/3] Instalando dependencias de build...
pip install -r requirements-dev.txt || goto :error

echo [2/3] Limpiando builds anteriores...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [3/3] Generando ejecutable con PyInstaller...
pyinstaller SmartManagerAI.spec --noconfirm || goto :error

echo.
echo  LISTO  ^>  dist\SmartManagerAI\SmartManagerAI.exe
echo  Recuerda copiar tu .env junto al .exe antes de distribuir.
goto :eof

:error
echo.
echo  ERROR en el build. Revisa los mensajes anteriores.
exit /b 1
