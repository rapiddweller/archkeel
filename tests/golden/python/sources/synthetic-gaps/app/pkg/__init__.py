try:
    from app.pkg.fast import helper
except ImportError:
    from app.pkg.slow import helper
