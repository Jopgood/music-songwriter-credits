"""Manual review interface package for the songwriter identification system."""

import os
import logging
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Import after environment is loaded
from songwriter_id.database.setup import setup_database
from songwriter_id.review_interface.app import create_app

# Set up database
engine = setup_database()
if not engine:
    logger.error("Failed to set up database. Interface may not function correctly.")

# Create app
app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
