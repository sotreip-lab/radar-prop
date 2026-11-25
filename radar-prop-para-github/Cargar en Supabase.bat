@echo off
title Radar Prop - Cargar en Supabase
cd /d "%~dp0"
set PYEXE=
if exist "..\BuscadorPropiedades\python_path.txt" set /p PYEXE=<"..\BuscadorPropiedades\python_path.txt"
if "%PYEXE%"=="" set PYEXE=py
echo Instalando lo necesario (solo la primera vez)...
"%PYEXE%" -m pip install --user --quiet --disable-pip-version-check sqlalchemy alembic geoalchemy2 pg8000
if errorlevel 1 ( echo No se pudo instalar. Revisa la conexion a internet. & pause & exit /b 1 )
"%PYEXE%" scripts\cargar_supabase.py
echo.
pause
