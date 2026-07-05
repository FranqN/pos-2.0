from flask import Blueprint, render_template, redirect

bp = Blueprint("landing", __name__)


@bp.route("/", methods=["GET"])
def home():
    return render_template("landing.html", title="Multi-tenant POS")


@bp.route("/landing", methods=["GET"])
def landing():
    # Keep both URLs working; best practice is a simple redirect.
    return redirect("/", code=302)
