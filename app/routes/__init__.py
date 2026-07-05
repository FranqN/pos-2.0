from .auth import bp as auth_bp
from .tenant import bp as tenant_bp
from .products import bp as products_bp
from .customers import bp as customers_bp
from .pos import bp as pos_bp
from .reports import bp as reports_bp
from .seed import bp as seed_bp
from .landing import bp as landing_bp
from .stock import bp as stock_bp
from .receipt import bp as receipt_bp
from .analytics import bp as analytics_bp


def register_blueprints(app):
    app.register_blueprint(auth_bp)
    app.register_blueprint(landing_bp, url_prefix="")
    app.register_blueprint(tenant_bp, url_prefix="/tenant")
    app.register_blueprint(products_bp, url_prefix="/products")
    app.register_blueprint(customers_bp, url_prefix="/customers")
    app.register_blueprint(pos_bp, url_prefix="/pos")
    app.register_blueprint(reports_bp, url_prefix="/reports")
    app.register_blueprint(seed_bp, url_prefix="")
    app.register_blueprint(stock_bp, url_prefix="/stock")
    app.register_blueprint(receipt_bp, url_prefix="/receipt")
    app.register_blueprint(analytics_bp, url_prefix="/analytics")
