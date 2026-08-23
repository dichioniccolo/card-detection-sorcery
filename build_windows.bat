@echo off
REM Costruisce CardsDetectionSorcery.exe (GUI, singolo file).
REM Da eseguire su Windows, in questa cartella, con Python 3.10+ installato.

echo === Creazione ambiente virtuale ===
python -m venv build-venv || goto :error

echo === Installazione dipendenze ===
build-venv\Scripts\python.exe -m pip install --upgrade pip || goto :error
build-venv\Scripts\python.exe -m pip install -r requirements.txt pyinstaller || goto :error

echo === Build ===
build-venv\Scripts\pyinstaller.exe --clean --noconfirm CardsDetectionSorcery.spec || goto :error

echo.
echo === Fatto: dist\CardsDetectionSorcery.exe ===
echo Questo file e' autonomo e puoi condividerlo cosi' com'e'.
pause
exit /b 0

:error
echo.
echo BUILD FALLITA. Controlla i messaggi qui sopra.
pause
exit /b 1
