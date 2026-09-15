@echo off
chcp 866 >nul
cd /d "%~dp0"
title Kategoriynaya analitika RTG
echo.
echo   ==================================
echo     КАТЕГОРИЙНАЯ АНАЛИТИКА РТГ
echo   ==================================
echo.
where python >nul 2>nul
if errorlevel 1 goto nopython
echo   Проверяю библиотеки...
python -m pip install --quiet --disable-pip-version-check -r requirements.txt
echo.
python engine/run.py %*
if errorlevel 1 goto failed
echo.
echo   Готово. Открываю папку с отчётами...
for /f "delims=" %%d in ('dir /b /ad /o-d "3_ОТЧЁТЫ" 2^>nul') do (
  start "" "%~dp03_ОТЧЁТЫ\%%d"
  goto done
)
goto done

:nopython
echo.
echo   ОШИБКА: Python не установлен.
echo   Скачайте с python.org и при установке отметьте
echo   галочку "Add Python to PATH".
goto done

:failed
echo.
echo   Расчёт остановлен. Причина указана выше.
goto done

:done
echo.
pause
