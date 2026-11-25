@echo off
title Radar Prop - Secretos para GitHub
cd /d "%~dp0"
set PYEXE=
if exist "..\BuscadorPropiedades\python_path.txt" set /p PYEXE=<"..\BuscadorPropiedades\python_path.txt"
if "%PYEXE%"=="" set PYEXE=py
"%PYEXE%" scripts\secretos_github.py
