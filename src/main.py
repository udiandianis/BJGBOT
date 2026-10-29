import logging
import threading
from src.app import create_app
from src.services.scheduler import run_daily_refresh

app = create_app()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    settings = app.extensions['bot_settings']
    stop_event = threading.Event()
    refresh_thread = threading.Thread(target=run_daily_refresh,
                                     args=(stop_event, settings.problemset_refresh_time),
                                     name='problemset-refresh', daemon=True)
    refresh_thread.start()
    try:
        app.run(host=settings.host, port=settings.port, debug=False, threaded=True)
    finally:
        stop_event.set()
        refresh_thread.join(timeout=2)
