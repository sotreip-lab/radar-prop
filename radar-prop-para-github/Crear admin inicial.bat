@echo off
title Radar Prop - Crear administrador inicial
cd /d "%~dp0"
set PYEXE=
if exist "..\BuscadorPropiedades\python_path.txt" set /p PYEXE=<"..\BuscadorPropiedades\python_path.txt"
if "%PYEXE%"=="" set PYEXE=py
"%PYEXE%" -m pip install --user --quiet --disable-pip-version-check sqlalchemy alembic geoalchemy2 pg8000 argon2-cffi
"%PYEXE%" scripts\crear_admin_inicial.py
echo.
pause
