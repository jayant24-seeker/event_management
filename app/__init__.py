from flask import Flask

from .events import EventStore


def create_app(config=None):
    app = Flask(__name__)
    app.config.update(SITE_NAME="Eventouse", EVENTS_FILE=None)
    if config:
        app.config.update(config)

    store = EventStore(app.config["EVENTS_FILE"]) if app.config["EVENTS_FILE"] else EventStore()
    for slug, issues in store.invalid.items():
        app.logger.warning("Hidden event %s: %s", slug, "; ".join(issues))
    app.extensions["events"] = store

    @app.template_filter("inr")
    def inr(amount):
        # Indian digit grouping: 1,00,000
        s = str(int(amount))
        if len(s) > 3:
            head, tail = s[:-3], s[-3:]
            groups = []
            while len(head) > 2:
                groups.insert(0, head[-2:])
                head = head[:-2]
            s = ",".join(([head] if head else []) + groups) + "," + tail
        return f"₹{s}"

    @app.context_processor
    def globals_():
        return {"site_name": app.config["SITE_NAME"]}

    from .routes import bp
    app.register_blueprint(bp)
    return app
