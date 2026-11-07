"""HTTP API layer - Flask, not the spec's originally-required FastAPI, because FastAPI isn't
installed in this sandbox (no network to pip install it). See docs/adr for the substitution
rationale and the migration path to FastAPI + Pydantic in a real deployment.

This wires: JWT bearer auth -> Principal, DomainError -> JSON/HTTP-status mapping, security
headers, and per-bucket rate limiting, then exposes a representative slice of endpoints across
every module so the pattern is provable end-to-end. Not every module method has a route here;
the ones that do are enough to demonstrate request parsing, auth, error mapping and idempotency
headers working together identically for every module.
"""
from __future__ import annotations

import functools
import time

from flask import Flask, g, jsonify, request

from .container import Container
from ..observability.logging import new_request_id
from ..observability.metrics import registry
from ..security.headers import SECURITY_HEADERS
from ..shared.errors import AuthenticationFailed, DomainError, RateLimited, ValidationFailed


def create_app(container: Container | None = None) -> Flask:
    app = Flask(__name__)
    c = container or Container()
    app.container = c

    @app.before_request
    def _start_request():
        g.request_id = new_request_id()
        g.request_start = time.monotonic()

    @app.after_request
    def add_security_headers(resp):
        for k, v in SECURITY_HEADERS.items():
            resp.headers[k] = v
        resp.headers["X-Request-Id"] = getattr(g, "request_id", "")
        origin = request.headers.get("Origin")
        if origin and origin in c.settings.cors_origins:
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Vary"] = "Origin"
            resp.headers["Access-Control-Allow-Credentials"] = "true"
            resp.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, Idempotency-Key"
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        elapsed = time.monotonic() - getattr(g, "request_start", time.monotonic())
        registry.increment("http_requests_total", route=request.url_rule.rule if request.url_rule else "unmatched",
                           method=request.method, status=str(resp.status_code))
        registry.observe("http_request_duration_seconds", elapsed,
                         route=request.url_rule.rule if request.url_rule else "unmatched")
        return resp

    @app.before_request
    def _handle_preflight():
        if request.method == "OPTIONS":
            return "", 204

    @app.errorhandler(DomainError)
    def handle_domain_error(err: DomainError):
        return jsonify({"error": {"code": err.code, "message": err.message, "details": err.details}}), err.http_status

    @app.errorhandler(404)
    def handle_404(_e):
        return jsonify({"error": {"code": "NOT_FOUND", "message": "resource not found", "details": {}}}), 404

    def rate_limited(bucket: str):
        def deco(fn):
            @functools.wraps(fn)
            def wrapper(*a, **kw):
                identity = getattr(g, "principal", None)
                key = identity.user_id if identity else (request.remote_addr or "anon")
                try:
                    c.rate_limiter.check(bucket, key)
                except RateLimited as e:
                    raise e
                return fn(*a, **kw)
            return wrapper
        return deco

    def require_auth(fn):
        @functools.wraps(fn)
        def wrapper(*a, **kw):
            auth = request.headers.get("Authorization", "")
            if not auth.startswith("Bearer "):
                raise AuthenticationFailed("missing bearer token")
            g.principal = c.identity.authenticate(auth[len("Bearer "):])
            return fn(*a, **kw)
        return wrapper

    def json_body() -> dict:
        body = request.get_json(silent=True)
        if body is None:
            raise ValidationFailed("request body must be valid JSON")
        return body

    def idem_key() -> str:
        key = request.headers.get("Idempotency-Key")
        if not key:
            raise ValidationFailed("Idempotency-Key header is required for this endpoint")
        return key

    # ----------------------------------------------------------------- health
    @app.get("/healthz")
    def healthz():
        return jsonify({"status": "ok"})

    @app.get("/metrics")
    def metrics():
        return registry.prometheus_text(), 200, {"Content-Type": "text/plain; version=0.0.4"}

    # ------------------------------------------------------------------ auth
    @app.post("/api/v1/auth/register")
    @rate_limited("default")
    def register():
        b = json_body()
        user = c.identity.register(phone=b.get("phone", ""), password=b.get("password", ""),
                                   full_name=b.get("full_name", ""), role=b.get("role", "BUYER"),
                                   email=b.get("email"))
        return jsonify(user), 201

    @app.post("/api/v1/auth/login")
    @rate_limited("login")
    def login():
        b = json_body()
        return jsonify(c.identity.login(phone=b.get("phone", ""), password=b.get("password", "")))

    @app.post("/api/v1/auth/refresh")
    @rate_limited("default")
    def refresh():
        b = json_body()
        return jsonify(c.identity.refresh(b.get("refresh_token", "")))

    @app.get("/api/v1/me")
    @require_auth
    def me():
        return jsonify(c.identity.get_profile(g.principal))

    # ------------------------------------------------------------- marketplace
    @app.get("/api/v1/crops")
    def list_crops():
        return jsonify(c.market.list_crops())

    @app.get("/api/v1/listings")
    @rate_limited("public_search")
    def search_listings():
        q = request.args
        near = None
        if q.get("lat") and q.get("lon") and q.get("radius_m"):
            near = (float(q["lat"]), float(q["lon"]), float(q["radius_m"]))
        return jsonify(c.market.search(text=q.get("q"), crop_id=q.get("crop_id"), state=q.get("state"),
                                       lga=q.get("lga"), near=near, sort=q.get("sort", "newest"),
                                       limit=int(q.get("limit", 20)), offset=int(q.get("offset", 0))))

    @app.post("/api/v1/listings")
    @require_auth
    @rate_limited("default")
    def create_listing():
        b = json_body()
        return jsonify(c.market.create_listing(g.principal, crop_id=b["crop_id"], title=b["title"],
                                               quantity=b["quantity"], unit=b["unit"], price=b["price"],
                                               state=b["state"], lga=b["lga"], farm_id=b.get("farm_id"))), 201

    @app.get("/api/v1/listings/<listing_id>")
    def get_listing(listing_id):
        return jsonify(c.market.get(listing_id))

    # ------------------------------------------------------------------ orders
    @app.post("/api/v1/orders")
    @require_auth
    @rate_limited("default")
    def create_order():
        b = json_body()
        return jsonify(c.orders.create(g.principal, listing_id=b["listing_id"], quantity=b["quantity"],
                                       delivery_address=b.get("delivery_address", ""))), 201

    @app.get("/api/v1/orders/<order_id>")
    @require_auth
    def get_order(order_id):
        return jsonify(c.orders.get(g.principal, order_id))

    @app.post("/api/v1/orders/<order_id>/confirm")
    @require_auth
    def confirm_order(order_id):
        return jsonify(c.orders.confirm(g.principal, order_id))

    @app.post("/api/v1/orders/<order_id>/fund")
    @require_auth
    @rate_limited("payment")
    def fund_order(order_id):
        return jsonify(c.orders.fund(g.principal, order_id))

    @app.post("/api/v1/orders/<order_id>/release")
    @require_auth
    @rate_limited("payment")
    def release_order(order_id):
        return jsonify(c.orders.release(g.principal, order_id, idempotency_key=idem_key()))

    # ---------------------------------------------------------------- payments
    @app.post("/api/v1/payments/charges")
    @require_auth
    @rate_limited("payment")
    def create_charge():
        b = json_body()
        return jsonify(c.payments.create_charge(g.principal, amount_minor=b["amount_minor"],
                                                order_id=b.get("order_id"))), 201

    @app.post("/api/v1/payments/webhook")
    @rate_limited("webhook")
    def payment_webhook():
        sig = request.headers.get("X-Signature", "")
        return jsonify(c.payments.handle_webhook(request.get_data(), sig))

    # ------------------------------------------------------------------- farms
    @app.post("/api/v1/farms")
    @require_auth
    @rate_limited("default")
    def create_farm():
        b = json_body()
        return jsonify(c.farms.create(g.principal, name=b["name"], state=b["state"], lga=b["lga"],
                                      size_hectares=b["size_hectares"], lat=b["lat"], lon=b["lon"])), 201

    @app.get("/api/v1/farms/<farm_id>")
    @require_auth
    def get_farm(farm_id):
        return jsonify(c.farms.get(g.principal, farm_id))

    # ------------------------------------------------------------- analytics
    @app.get("/api/v1/analytics/me")
    @require_auth
    def analytics_me():
        return jsonify(c.analytics.farmer_dashboard(g.principal))

    @app.get("/api/v1/analytics/buyer")
    @require_auth
    def analytics_buyer():
        return jsonify(c.analytics.buyer_dashboard(g.principal))

    @app.get("/api/v1/analytics/platform")
    @require_auth
    def analytics_platform():
        return jsonify(c.analytics.platform_overview(g.principal))

    @app.get("/api/v1/analytics/ops")
    @require_auth
    def analytics_ops():
        return jsonify(c.analytics.ops_queue_depths(g.principal))

    @app.get("/api/v1/analytics/lenders/<org_id>")
    @require_auth
    def analytics_lender(org_id):
        return jsonify(c.analytics.lender_portfolio(g.principal, org_id))

    # ---------------------------------------------------------- more: orders
    @app.get("/api/v1/orders")
    @require_auth
    def list_orders():
        role = request.args.get("role", "buyer")
        return jsonify(c.orders.list_mine(g.principal, role=role, state=request.args.get("state")))

    @app.post("/api/v1/orders/<order_id>/prepare")
    @require_auth
    def prepare_order(order_id):
        return jsonify(c.orders.prepare(g.principal, order_id))

    @app.post("/api/v1/orders/<order_id>/dispatch")
    @require_auth
    def dispatch_order(order_id):
        return jsonify(c.orders.dispatch(g.principal, order_id))

    @app.post("/api/v1/orders/<order_id>/delivery-failed")
    @require_auth
    def delivery_failed_order(order_id):
        b = json_body()
        return jsonify(c.orders.delivery_failed(g.principal, order_id, b.get("reason", "")))

    @app.post("/api/v1/orders/<order_id>/deliver")
    @require_auth
    def deliver_order(order_id):
        b = json_body()
        return jsonify(c.orders.mark_delivered(g.principal, order_id, b["delivered_quantity"]))

    @app.post("/api/v1/orders/<order_id>/inspect")
    @require_auth
    def inspect_order(order_id):
        b = json_body()
        return jsonify(c.orders.inspect(g.principal, order_id, b["accepted_quantity"], b.get("quality_result", "")))

    @app.post("/api/v1/orders/<order_id>/cancel")
    @require_auth
    def cancel_order(order_id):
        b = json_body()
        return jsonify(c.orders.cancel(g.principal, order_id, b.get("reason", "")))

    @app.post("/api/v1/orders/<order_id>/disputes")
    @require_auth
    def open_dispute(order_id):
        b = json_body()
        return jsonify(c.orders.open_dispute(g.principal, order_id, b.get("reason", ""))), 201

    @app.post("/api/v1/disputes/<dispute_id>/resolve")
    @require_auth
    def resolve_dispute(dispute_id):
        b = json_body()
        return jsonify(c.orders.resolve_dispute(g.principal, dispute_id, seller_amount_minor=b["seller_amount_minor"],
                                                buyer_amount_minor=b["buyer_amount_minor"],
                                                resolution=b.get("resolution", "")))

    @app.get("/api/v1/disputes")
    @require_auth
    def list_disputes():
        return jsonify(c.orders.list_disputes(g.principal))

    @app.get("/api/v1/disputes/<dispute_id>")
    @require_auth
    def get_dispute(dispute_id):
        return jsonify(c.orders.get_dispute(g.principal, dispute_id))

    @app.get("/api/v1/orders/<order_id>/escrow")
    @require_auth
    def get_escrow(order_id):
        return jsonify(c.escrow.get_for_order(g.principal, order_id))

    # -------------------------------------------------------------- payments
    @app.get("/api/v1/payments/<payment_id>")
    @require_auth
    def get_payment(payment_id):
        return jsonify(c.payments.get(g.principal, payment_id))

    @app.post("/api/v1/payments/payouts")
    @require_auth
    @rate_limited("payment")
    def request_payout():
        b = json_body()
        return jsonify(c.payments.request_payout(g.principal, amount_minor=b["amount_minor"],
                                                 destination=b["destination"], client_ref=b["client_ref"])), 201

    # -------------------------------------------------------- organizations
    @app.post("/api/v1/organizations")
    @require_auth
    @rate_limited("default")
    def create_org():
        b = json_body()
        return jsonify(c.organizations.create(g.principal, name=b["name"], type=b["type"], state=b.get("state"),
                                              lga=b.get("lga"))), 201

    @app.get("/api/v1/organizations/mine")
    @require_auth
    def my_orgs():
        return jsonify(c.organizations.mine(g.principal))

    @app.get("/api/v1/organizations")
    @require_auth
    def list_all_orgs():
        return jsonify(c.organizations.list_all(g.principal))

    @app.get("/api/v1/organizations/<org_id>")
    @require_auth
    def get_org(org_id):
        return jsonify(c.organizations.get(g.principal, org_id))

    @app.post("/api/v1/organizations/<org_id>/members")
    @require_auth
    def add_org_member(org_id):
        b = json_body()
        c.organizations.add_member(g.principal, org_id, b["user_id"], b.get("org_role", "MEMBER"))
        return jsonify({"status": "added"}), 201

    # ------------------------------------------------------------------- farms
    @app.get("/api/v1/farms")
    @require_auth
    def list_my_farms():
        return jsonify(c.farms.list_mine(g.principal))

    @app.get("/api/v1/farms/nearby")
    def farms_nearby():
        q = request.args
        return jsonify(c.farms.nearby(float(q["lat"]), float(q["lon"]), float(q.get("radius_km", 25))))

    @app.post("/api/v1/farms/<farm_id>/request-verification")
    @require_auth
    def request_farm_verification(farm_id):
        return jsonify(c.farms.request_verification(g.principal, farm_id))

    @app.post("/api/v1/farms/<farm_id>/assign-agent")
    @require_auth
    def assign_farm_agent(farm_id):
        b = json_body()
        return jsonify(c.farms.assign_agent(g.principal, farm_id, b["agent_id"]))

    @app.post("/api/v1/farms/<farm_id>/visits")
    @require_auth
    def record_farm_visit(farm_id):
        b = json_body()
        return jsonify(c.farms.record_visit(g.principal, farm_id, lat=b["lat"], lon=b["lon"],
                                            client_id=b["client_id"], observations=b.get("observations", ""))), 201

    @app.post("/api/v1/farms/<farm_id>/submit")
    @require_auth
    def submit_farm(farm_id):
        return jsonify(c.farms.submit(g.principal, farm_id))

    @app.post("/api/v1/farms/<farm_id>/verify")
    @require_auth
    def verify_farm(farm_id):
        b = request.get_json(silent=True) or {}
        return jsonify(c.farms.verify(g.principal, farm_id, b.get("notes", "")))

    @app.post("/api/v1/farms/<farm_id>/reject")
    @require_auth
    def reject_farm(farm_id):
        b = json_body()
        return jsonify(c.farms.reject(g.principal, farm_id, b.get("reason", "")))

    # ------------------------------------------------------------ traceability
    @app.post("/api/v1/lots")
    @require_auth
    @rate_limited("default")
    def create_lot():
        b = json_body()
        return jsonify(c.traceability.create_lot(g.principal, farm_id=b["farm_id"], crop_id=b["crop_id"],
                                                 quantity=b["quantity"], unit=b["unit"],
                                                 harvest_date=b["harvest_date"],
                                                 quality_grade=b.get("quality_grade", "UNGRADED"))), 201

    @app.get("/api/v1/lots")
    @require_auth
    def list_lots():
        farm_id = request.args.get("farm_id") or None
        return jsonify(c.traceability.list_lots(g.principal, farm_id=farm_id))

    @app.get("/api/v1/lots/<lot_id>")
    def get_lot(lot_id):
        return jsonify(c.traceability.get_lot(lot_id))

    @app.get("/api/v1/lots/by-code/<code>")
    def get_lot_by_code(code):
        return jsonify(c.traceability.get_by_code(code))

    @app.get("/api/v1/lots/<lot_id>/history")
    def lot_history(lot_id):
        ok, bad_id = c.traceability.verify_chain(lot_id)
        return jsonify({"events": c.traceability.history(lot_id), "chain_valid": ok, "first_tampered_id": bad_id})

    @app.post("/api/v1/lots/<lot_id>/weighing")
    @require_auth
    def record_weighing(lot_id):
        b = json_body()
        return jsonify(c.traceability.record_weighing(g.principal, lot_id, gross_kg=b["gross_kg"],
                                                       tare_kg=b["tare_kg"], warehouse_id=b.get("warehouse_id"))), 201

    @app.post("/api/v1/lots/<lot_id>/inspection")
    @require_auth
    def record_lot_inspection(lot_id):
        b = json_body()
        return jsonify(c.traceability.record_inspection(g.principal, lot_id, grade=b["grade"], passed=b["passed"],
                                                         moisture_pct=b.get("moisture_pct"),
                                                         defects_pct=b.get("defects_pct"),
                                                         notes=b.get("notes", ""))), 201

    # -------------------------------------------------------------- inventory
    @app.post("/api/v1/warehouses")
    @require_auth
    def create_warehouse():
        b = json_body()
        return jsonify(c.inventory.create_warehouse(g.principal, org_id=b["org_id"], name=b["name"],
                                                    state=b.get("state"), lga=b.get("lga"))), 201

    @app.post("/api/v1/inventory/movements")
    @require_auth
    def record_inventory_movement():
        b = json_body()
        return jsonify(c.inventory.move(g.principal, warehouse_id=b["warehouse_id"], lot_id=b["lot_id"],
                                        movement_type=b["movement_type"], qty_delta=b["qty_delta"],
                                        reason=b["reason"])), 201

    # -------------------------------------------------------------- logistics
    @app.post("/api/v1/vehicles")
    @require_auth
    def register_vehicle():
        b = json_body()
        return jsonify(c.logistics.register_vehicle(g.principal, org_id=b["org_id"], plate=b["plate"],
                                                     vehicle_type=b["vehicle_type"],
                                                     capacity_kg=b["capacity_kg"])), 201

    @app.get("/api/v1/vehicles")
    @require_auth
    def list_vehicles():
        org_id = request.args.get("org_id", "")
        if not org_id:
            raise ValidationFailed("org_id query parameter is required")
        return jsonify(c.logistics.list_vehicles(g.principal, org_id))

    @app.post("/api/v1/drivers")
    @require_auth
    def register_driver():
        b = json_body()
        return jsonify(c.logistics.register_driver(g.principal, org_id=b["org_id"], name=b["name"],
                                                    phone=b["phone"], user_id=b.get("user_id"))), 201

    @app.get("/api/v1/drivers")
    @require_auth
    def list_drivers():
        org_id = request.args.get("org_id", "")
        if not org_id:
            raise ValidationFailed("org_id query parameter is required")
        return jsonify(c.logistics.list_drivers(g.principal, org_id))

    @app.get("/api/v1/shipments")
    @require_auth
    def list_shipments():
        return jsonify(c.logistics.list_shipments(g.principal))

    @app.post("/api/v1/shipments")
    @require_auth
    def request_shipment():
        b = json_body()
        return jsonify(c.logistics.request(g.principal, order_id=b["order_id"], pickup_lat=b["pickup_lat"],
                                           pickup_lon=b["pickup_lon"], dropoff_lat=b["dropoff_lat"],
                                           dropoff_lon=b["dropoff_lon"])), 201

    @app.post("/api/v1/shipments/<shipment_id>/assign")
    @require_auth
    def assign_shipment(shipment_id):
        b = json_body()
        return jsonify(c.logistics.assign(g.principal, shipment_id, driver_id=b["driver_id"],
                                          vehicle_id=b["vehicle_id"], provider_org_id=b["provider_org_id"]))

    @app.post("/api/v1/shipments/<shipment_id>/picked-up")
    @require_auth
    def shipment_picked_up(shipment_id):
        b = json_body()
        return jsonify(c.logistics.mark_picked_up(g.principal, shipment_id, b["lat"], b["lon"]))

    @app.post("/api/v1/shipments/<shipment_id>/in-transit")
    @require_auth
    def shipment_in_transit(shipment_id):
        return jsonify(c.logistics.mark_in_transit(g.principal, shipment_id))

    @app.post("/api/v1/shipments/<shipment_id>/delivered")
    @require_auth
    def shipment_delivered(shipment_id):
        b = json_body()
        return jsonify(c.logistics.mark_delivered(g.principal, shipment_id, b["lat"], b["lon"]))

    @app.post("/api/v1/shipments/<shipment_id>/confirm")
    @require_auth
    def shipment_confirm(shipment_id):
        return jsonify(c.logistics.confirm(g.principal, shipment_id))

    @app.post("/api/v1/shipments/<shipment_id>/failed")
    @require_auth
    def shipment_failed(shipment_id):
        b = json_body()
        return jsonify(c.logistics.mark_failed(g.principal, shipment_id, b.get("reason", "")))

    @app.get("/api/v1/shipments/<shipment_id>/track")
    @require_auth
    def shipment_track(shipment_id):
        return jsonify(c.logistics.track(g.principal, shipment_id))

    # --------------------------------------------------------------- lending
    @app.post("/api/v1/loan-products")
    @require_auth
    def create_loan_product():
        b = json_body()
        return jsonify(c.lending.create_product(
            g.principal, lender_org_id=b["lender_org_id"], name=b["name"],
            min_amount_minor=b["min_amount_minor"], max_amount_minor=b["max_amount_minor"],
            min_term_months=b["min_term_months"], max_term_months=b["max_term_months"],
            annual_rate_bps=b["annual_rate_bps"], late_fee_bps=b.get("late_fee_bps", 0),
            min_credit_score=b.get("min_credit_score", 0),
            requires_verified_farm=b.get("requires_verified_farm", True))), 201

    @app.get("/api/v1/loan-products")
    @require_auth
    def list_loan_products():
        lender_org_id = request.args.get("lender_org_id") or None
        return jsonify(c.lending.list_products(lender_org_id))

    @app.post("/api/v1/loan-applications")
    @require_auth
    @rate_limited("default")
    def apply_for_loan():
        b = json_body()
        return jsonify(c.lending.apply(g.principal, product_id=b["product_id"], amount_minor=b["amount_minor"],
                                       term_months=b["term_months"], purpose=b.get("purpose", ""))), 201

    @app.get("/api/v1/loan-applications")
    @require_auth
    def list_loan_applications():
        return jsonify(c.lending.list_applications(g.principal))

    @app.post("/api/v1/loan-applications/<application_id>/decide")
    @require_auth
    def decide_loan_application(application_id):
        b = json_body()
        return jsonify(c.lending.decide(g.principal, application_id, approve=b["approve"], reason=b.get("reason", ""),
                                        override=b.get("override", False)))

    @app.post("/api/v1/loan-applications/<application_id>/disburse")
    @require_auth
    def disburse_loan(application_id):
        return jsonify(c.lending.disburse(g.principal, application_id, idempotency_key=idem_key()))

    @app.get("/api/v1/loans")
    @require_auth
    def list_loans():
        return jsonify(c.lending.list_loans(g.principal))

    @app.get("/api/v1/loans/<loan_id>")
    @require_auth
    def get_loan(loan_id):
        return jsonify(c.lending.get_loan(g.principal, loan_id))

    @app.get("/api/v1/loans/<loan_id>/schedule")
    @require_auth
    def loan_schedule(loan_id):
        return jsonify(c.lending.schedule(g.principal, loan_id))

    @app.post("/api/v1/loans/<loan_id>/repay")
    @require_auth
    @rate_limited("payment")
    def repay_loan(loan_id):
        b = json_body()
        return jsonify(c.lending.repay(g.principal, loan_id, b["amount_minor"], idempotency_key=idem_key()))

    @app.get("/api/v1/credit/me")
    @require_auth
    def my_credit():
        return jsonify(c.lending.credit_view(g.principal, g.principal.user_id))

    # -------------------------------------------------------------- insurance
    @app.post("/api/v1/insurance/policies")
    @require_auth
    def buy_policy():
        b = json_body()
        return jsonify(c.insurance.buy_policy(
            g.principal, farm_id=b["farm_id"], coverage_minor=b["coverage_minor"],
            premium_minor=b["premium_minor"], trigger_metric=b["trigger_metric"], comparator=b["comparator"],
            threshold=b["threshold"], window_start=b["window_start"], window_end=b["window_end"])), 201

    @app.get("/api/v1/insurance/policies")
    @require_auth
    def list_insurance_policies():
        return jsonify(c.insurance.list_policies(g.principal))

    @app.post("/api/v1/insurance/policies/<policy_id>/pay-premium")
    @require_auth
    @rate_limited("payment")
    def pay_premium(policy_id):
        return jsonify(c.insurance.pay_premium(g.principal, policy_id))

    @app.get("/api/v1/insurance/policies/<policy_id>")
    @require_auth
    def get_policy(policy_id):
        return jsonify(c.insurance.get(g.principal, policy_id))

    # ------------------------------------------------------------ offline sync
    @app.post("/api/v1/sync/batch")
    @require_auth
    def sync_batch():
        b = json_body()
        return jsonify(c.offline_sync.apply_batch(g.principal, b["device_id"], b["operations"]))

    @app.get("/api/v1/sync/status")
    @require_auth
    def sync_status():
        device_id = request.args.get("device_id", "")
        op_ids = request.args.getlist("operation_id")
        return jsonify(c.offline_sync.pending_status(device_id, op_ids))

    # -------------------------------------------------------------- notifications
    @app.get("/api/v1/notifications")
    @require_auth
    def notifications_inbox():
        unread_only = request.args.get("unread_only") == "true"
        return jsonify(c.notifications.inbox(g.principal.user_id, unread_only=unread_only))

    @app.post("/api/v1/notifications/<notification_id>/read")
    @require_auth
    def mark_notification_read(notification_id):
        c.notifications.mark_read(g.principal.user_id, notification_id)
        return jsonify({"status": "read"})

    # -------------------------------------------------------------------- ml
    @app.get("/api/v1/farms/<farm_id>/yield-prediction")
    @require_auth
    def predict_yield(farm_id):
        return jsonify(c.ml.predict_yield(g.principal, farm_id))

    # ------------------------------------------------------------------ admin
    @app.get("/api/v1/admin/users")
    @require_auth
    def admin_list_users():
        q = request.args
        return jsonify(c.admin.list_users(g.principal, status=q.get("status"), role=q.get("role"),
                                          limit=int(q.get("limit", 50)), offset=int(q.get("offset", 0))))

    @app.get("/api/v1/admin/users/<user_id>")
    @require_auth
    def admin_user_detail(user_id):
        return jsonify(c.admin.user_detail(g.principal, user_id))

    @app.get("/api/v1/admin/audit")
    @require_auth
    def admin_audit_trail():
        q = request.args
        return jsonify(c.admin.audit_trail(g.principal, resource_type=q.get("resource_type"),
                                           resource_id=q.get("resource_id"), actor_id=q.get("actor_id"),
                                           limit=int(q.get("limit", 100))))

    # ------------------------------------------------------ dev-only test helpers
    # Mirrors the "test mode" simulate-success action real payment gateways (Paystack,
    # Flutterwave) provide in their sandboxes: with a mocked provider there is otherwise no way
    # to drive the success/webhook path from outside the Python process (unlike the real
    # gateway's hosted checkout page, which calls our webhook after the user actually pays).
    # Disabled outside development/testing so it can never exist in a real deployment.
    if c.settings.env in ("development", "testing"):
        @app.post("/api/v1/_dev/payments/simulate-success")
        def dev_simulate_payment_success():
            b = json_body()
            c.payment_provider.simulate_success(b["reference"], amount_minor=b.get("amount_minor"))
            return jsonify({"status": "simulated", "reference": b["reference"]})

        @app.post("/api/v1/_dev/payments/simulate-failure")
        def dev_simulate_payment_failure():
            b = json_body()
            c.payment_provider.simulate_failure(b["reference"])
            return jsonify({"status": "simulated", "reference": b["reference"]})

        @app.post("/api/v1/_dev/payments/webhook-signature")
        def dev_webhook_signature():
            """Lets an HTTP client (Postman) get a correctly-signed webhook body without
            implementing the signing algorithm itself - signs whatever body is posted here."""
            sig = c.payment_provider.sign(request.get_data())
            return jsonify({"signature": sig})

        @app.post("/api/v1/_dev/time/advance")
        def dev_advance_time():
            """The sandbox FrozenClock-style time travel tests use isn't available against a
            running server (it uses a real SystemClock) - insurance window evaluation and loan
            overdue detection both depend on real time passing, so this only works here if the
            container's clock supports it. Against the default SystemClock this is a no-op that
            reports the current time, which is itself useful for confirming what "now" the
            server sees."""
            return jsonify({"now": c.ctx.now_iso(), "note": "SystemClock cannot be fast-forwarded;"
                            " use a window_end in the past when creating test insurance policies instead"})

    return app
