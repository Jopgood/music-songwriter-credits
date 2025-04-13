"""Manual review interface package for the songwriter identification system."""

from songwriter_id.review_interface.app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
