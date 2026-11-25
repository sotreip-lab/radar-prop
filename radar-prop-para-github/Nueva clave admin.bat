@echo off
title Radar Prop - Nueva clave de administrador
cd /d "%~dp0"
set PYEXE=
if exist "..\BuscadorPropiedades\python_path.txt" set /p PYEXE=<"..\BuscadorPropiedades\python_path.txt"
if "%PYEXE%"=="" set PYEXE=py
"%PYEXE%" scripts\crear_admin_inicial.py --nueva-clave bautista
echo.
pause
