from dotenv import load_dotenv

load_dotenv()

from flask import Flask, jsonify, render_template, request  # noqa: E402

from . import plaid_client, tokens  # noqa: E402


def create_link_token(institution, products=None):
    resp = plaid_client.create_link_token(
        user_id=f"finance-tracker-{institution}",
        products=products or ["transactions"],
        institution=institution,
    )
    return resp["link_token"]


def exchange_public_token(public_token):
    resp = plaid_client.exchange_public_token(public_token)
    return resp["access_token"], resp["item_id"]


def save_token(institution, access_token, item_id):
    tokens.save_token(institution, access_token=access_token, item_id=item_id)


def create_app():
    app = Flask(__name__)

    @app.get("/")
    def index():
        institution = request.args.get("institution")
        if not institution:
            return jsonify({"error": "institution query param required"}), 400
        link_token = create_link_token(institution)
        return render_template("link.html", institution=institution, link_token=link_token)

    @app.post("/exchange")
    def exchange():
        data = request.get_json(silent=True) or request.form or {}
        institution = data.get("institution")
        public_token = data.get("public_token")
        if not institution or not public_token:
            return jsonify({"error": "institution and public_token required"}), 400
        access_token, item_id = exchange_public_token(public_token)
        save_token(institution, access_token, item_id)
        return jsonify({"status": "ok", "institution": institution, "item_id": item_id})

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=False)
