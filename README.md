# Music Songwriter Credits Identification System

An automated system designed to identify songwriter credits for a music catalog of approximately 30,000 tracks using a multi-tiered approach combining database queries, machine learning, and audio fingerprinting.

## Project Overview

This system aims to streamline the process of identifying songwriter credits by implementing a four-tier identification approach:

1. **Tier 1: Metadata-Based Identification (50-70% resolution)**
   - Utilize existing track titles and artist information
   - Query established music databases like MusicBrainz (API or direct database access)
   - Match against PRO databases (ASCAP, BMI, SESAC, etc.)

2. **Tier 2: Enhanced Matching (15-25% additional resolution)**
   - Apply fuzzy text matching for titles/artists with variations
   - Implement ML-based normalization and entity resolution
   - Use pattern recognition for songwriter credit prediction

3. **Tier 3: Audio Content Analysis (5-10% additional resolution)**
   - Apply audio fingerprinting for unresolved tracks
   - Utilize acoustic feature analysis to find matches

4. **Tier 4: Manual Review (5-15% of catalog)**
   - Human verification for remaining unresolved tracks
   - Intuitive UI for efficient review process

## System Architecture

![System Architecture](docs/images/architecture.png)

The system follows a modular pipeline architecture that processes tracks sequentially through the tiers, stopping when a high-confidence match is found.

### Core Components

- **Data Ingestion Pipeline**: Process and normalize input catalog metadata
- **Database Layer**: Store tracks, identification attempts, and songwriter credits
- **API Integration Layer**: Connect to external music databases and PROs
- **ML Processing Engine**: Handle entity resolution and songwriter prediction
- **Audio Fingerprinting Service**: Process audio files for content-based matching
- **Confidence Scoring System**: Evaluate and combine results from multiple sources
- **Manual Review Interface**: UI for human verification of low-confidence matches
- **Web Interface**: Full-featured web UI for triggering the pipeline and monitoring results

## Technology Stack

- **Programming Language**: Python 3.10+
- **Database**: PostgreSQL 14+
- **ML Frameworks**: Scikit-learn, PyTorch
- **Audio Processing**: Librosa, AcoustID/Chromaprint
- **API Clients**: Requests, aiohttp
- **Web Interface**: Flask
- **Containerization**: Docker

## Setup Instructions

### Prerequisites

- Python 3.10+
- PostgreSQL 14+
- Docker and Docker Compose
- Chromaprint library (for audio fingerprinting)

### Installation

1. Clone this repository:
   ```
   git clone https://github.com/Jopgood/music-songwriter-credits.git
   cd music-songwriter-credits
   ```

2. Create and activate a virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\\Scripts\\activate
   ```

3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Set up the database:
   ```
   python scripts/setup_database.py
   ```

5. Configure API keys and database connections:
   - Copy `.env.example` to `.env`
   - Fill in your API keys for MusicBrainz, AcoustID, and PRO databases
   - Update configuration in `config/pipeline.yaml`

### MusicBrainz Database Integration

The system now supports direct connection to a MusicBrainz database, which significantly improves query speed and removes API rate limits. To use this feature:

1. Configure the MusicBrainz database connection in `config/pipeline.yaml`:
   ```yaml
   apis:
     musicbrainz:
       enabled: true
       client_type: "database"
       database:
         connection_string: "postgresql://musicbrainz:musicbrainz@localhost:5432/musicbrainz"
         pool_size: 10
         max_overflow: 20
   ```

2. Make sure the MusicBrainz database is accessible (e.g., running in Docker)

See the [MusicBrainz Database Integration](docs/musicbrainz_db_integration.md) documentation for more details.

### Running with Docker

1. Build the Docker containers:
   ```
   docker-compose build
   ```

2. Start the services:
   ```
   docker-compose up -d
   ```

## Usage

### Web Interface

The system includes a comprehensive web interface for managing the identification process:

1. Start the web interface:
   ```bash
   python -m songwriter_id.review_interface
   ```

2. Navigate to http://localhost:5000 in your browser

3. From the web interface, you can:
   - Upload and process music catalogs
   - Monitor pipeline progress
   - View identification statistics
   - Perform manual review of tracks
   - Browse all tracks and songwriter credits

For detailed documentation on the web interface, see [Web Interface Documentation](songwriter_id/review_interface/README.md).

### Command-Line Usage

#### Importing a Music Catalog

The system also includes a command-line script for importing music catalogs:

```bash
python scripts/import_catalog.py path/to/catalog.csv --audio-path /path/to/audio/files
```

Options:
- `--config`: Path to the configuration file (default: config/pipeline.yaml)
- `--db`: Database connection string
- `--audio-path`: Base path for audio files
- `--log-level`: Logging level (DEBUG, INFO, WARNING, ERROR)

#### Testing the Pipeline

You can test the pipeline with the included test script:

```bash
python scripts/test_pipeline.py --catalog data/sample_catalog.csv
```

Options:
- `--catalog`: Path to the test catalog file
- `--config`: Path to the configuration file
- `--db`: Database connection string

### Supported Catalog Formats

The data ingestion pipeline supports:
- CSV files with various delimiters (auto-detected)
- Excel files (.xlsx, .xls)

The system will automatically map common column names to standardized fields:
- Title: 'title', 'track_title', 'track name', 'name'
- Artist: 'artist', 'artist_name', 'performer'
- Album: 'album', 'release', 'release_title'
- Duration: 'duration', 'length', 'time'
- Audio Path: 'file', 'path', 'audio_path'
- ISRC: 'isrc', 'isrc_code', 'recording_code'

### Track Identification

The system identifies tracks using a combination of:
1. ISRC (International Standard Recording Code) - primary identifier when available
2. Title and artist name combination
3. Fuzzy matching when exact matches are not found

This approach ensures maximum coverage and allows processing of the full 30k catalog with proper deduplication.

### Processing a Catalog Programmatically

```python
from songwriter_id.pipeline import SongwriterIdentificationPipeline

# Initialize the pipeline
pipeline = SongwriterIdentificationPipeline(
    config_file="config/pipeline.yaml",
    db_connection="postgresql://user:password@localhost:5432/songwriter_db"
)

# Process a catalog
stats = pipeline.process_catalog(
    catalog_path="path/to/catalog.csv",
    audio_base_path="/path/to/audio/files"
)

# Check the results
print(f"Tracks added: {stats['import']['tracks_added']}")
print(f"Tier 1 identified: {stats['identification']['tier1_identified']}")
```

## Project Structure

```
music-songwriter-credits/
├── config/                     # Configuration files
│   └── pipeline.yaml           # Pipeline configuration
├── data/                       # Sample data and database migrations
├── docs/                       # Documentation and diagrams
│   └── musicbrainz_db_integration.md  # MusicBrainz DB integration docs
├── notebooks/                  # Jupyter notebooks for exploration
├── scripts/                    # Utility scripts
│   ├── import_catalog.py       # Catalog import script
│   └── test_pipeline.py        # Pipeline test script
├── songwriter_id/              # Main package
│   ├── __init__.py
│   ├── api/                    # API integration modules
│   │   ├── musicbrainz.py      # MusicBrainz API client
│   │   ├── musicbrainz_db.py   # MusicBrainz database client
│   │   └── acoustid.py         # AcoustID client 
│   ├── audio/                  # Audio processing modules
│   ├── data_ingestion/         # Data ingestion components
│   │   ├── __init__.py
│   │   ├── parser.py           # Catalog file parser
│   │   ├── normalizer.py       # Track metadata normalizer
│   │   └── importer.py         # Database importer
│   ├── database/               # Database models and utilities
│   ├── ml/                     # Machine learning components
│   ├── pipeline.py             # Main pipeline implementation
│   └── review_interface/       # Manual review UI and pipeline interface
├── tests/                      # Test suite
│   └── test_data_ingestion.py  # Tests for data ingestion
├── .env.example                # Example environment variables
├── docker-compose.yml          # Docker composition
├── Dockerfile                  # Docker configuration
├── pyproject.toml              # Project metadata
└── requirements.txt            # Python dependencies
```

## API Integrations

The system integrates with the following external services:

- **MusicBrainz**: 
  - API client for the open-source music metadata database
  - Direct database connection for faster queries (new feature)
- **AcoustID**: Open-source audio fingerprinting
- **PRO Databases**: ASCAP, BMI, SESAC, PRS, SOCAN, SACEM, GEMA
- **Music Publishing Databases**: Music Reports, Songtrust, ICE Services
- **Secondary Sources**: Discogs, AllMusic, Spotify, Apple Music

## Performance Improvements

The MusicBrainz database integration significantly improves identification performance:

- **No rate limiting**: Not limited by MusicBrainz API's 1 request per second
- **Reduced latency**: Local database connections eliminate network overhead
- **Complex queries**: Direct SQL allows more sophisticated querying than the API
- **Connection pooling**: Efficient database connections for batch processing

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- MusicBrainz for their comprehensive music metadata database
- AcoustID for audio fingerprinting capabilities
- Various PROs for songwriter data access
