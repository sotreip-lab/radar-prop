"""Configuración leída de variables de entorno (o de un archivo .env). Nunca hay claves en el código."""
import secrets

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore")

    # postgresql+psycopg://usuario:clave@host:5432/base
    database_url: str = "postgresql+psycopg://postgres@localhost:5432/radar"
    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_statement_timeout_ms: int = 15000

    # seguridad
    jwt_secret: str = ""                 # obligatorio en producción (si falta, se genera uno al arrancar)
    access_minutos: int = 15
    refresh_dias: int = 30
    cookie_secure: bool = True           # en desarrollo local por http: COOKIE_SECURE=false
    cookie_path: str = "/auth"           # detrás del proxy de Netlify (/api/* → API): COOKIE_PATH=/api/auth
    login_max_intentos: int = 5
    bloqueo_minutos: int = 15
    auth_pedidos_por_minuto: int = 20    # límite por IP en /auth/*
    frontend_origin: str = "http://localhost:5173"
    app_url: str = "https://radarprop.app"  # se usa en el texto de WhatsApp al crear usuarios

    # integraciones
    panel_url: str = "https://badenheuer-fichas.netlify.app"
    panel_ruta: str = "/panel-8yyp70b939mf/"
    panel_token: str = ""
    ia_api_key: str = ""


settings = Settings()
if not settings.jwt_secret:
    settings.jwt_secret = secrets.token_urlsafe(48)  # solo desarrollo: los tokens se invalidan al reiniciar
