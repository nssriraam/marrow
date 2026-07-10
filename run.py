"""
Marrow -- Application Entry Point

Starts the Flask development server.
"""

from flask import Flask
from app.config import Config
from app.routes import bp
from app import models
from flask_wtf.csrf import CSRFProtect


def create_app() -> Flask:
    """Application factory."""
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.secret_key = Config.FLASK_SECRET_KEY

    # Initialize database
    models.init_db()
    
    # Initialize CSRF protection
    CSRFProtect(app)

    @app.context_processor
    def inject_demo_mode():
        key = Config.FIREWORKS_API_KEY or ""
        is_demo = not key or key == "your_fireworks_api_key_here" or key.startswith("your_")
        return {"demo_mode": is_demo}

    # Register blueprint
    app.register_blueprint(bp)

    return app


if __name__ == "__main__":
    app = create_app()
    import os
    host = os.getenv("FLASK_RUN_HOST", "127.0.0.1")
    app.run(debug=Config.FLASK_DEBUG, host=host, port=5005)
