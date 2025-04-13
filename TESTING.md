# Testing the Music Songwriter Credits Identification System

This document provides instructions for testing the system with a sample music catalog.

## Prerequisites

1. Python 3.10+
2. Dependencies installed (`pip install -r requirements.txt`)
3. Database configured (SQLite database will be created automatically)

## Setting Up

1. Clone the repository:
   ```
   git clone https://github.com/Jopgood/music-songwriter-credits.git
   cd music-songwriter-credits
   ```

2. Create and activate a virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Create a `.env` file based on the `.env.example` template:
   ```
   cp .env.example .env
   ```

   Edit the `.env` file to add your API keys if you have them. For testing without actual API keys, the system will still process tracks but won't be able to make actual API calls (which is fine for initial testing).

## Running the Test Pipeline

Run the test script to process the sample music catalog:

```
python scripts/test_pipeline.py
```

This will:
1. Set up a SQLite database at `data/test_songwriter.db`
2. Initialize the pipeline
3. Process the sample catalog (`data/sample_catalog.csv`)
4. Report statistics on the processing

## Options

You can customize the test by specifying options:

```
python scripts/test_pipeline.py --catalog data/your_custom_catalog.csv --config config/your_config.yaml --db sqlite:///path/to/your/db.sqlite
```

- `--catalog`: Path to the catalog file (default: `data/sample_catalog.csv`)
- `--config`: Path to the configuration file (default: `config/pipeline.yaml`)
- `--db`: Database connection string (default: `sqlite:///data/test_songwriter.db`)

## Expected Output

The test should output processing statistics including:
- Number of tracks processed
- Import statistics (tracks added, skipped, errors)
- Identification statistics (tracks identified by tier, tracks requiring manual review)
- Database statistics (counts by identification status, top identified songwriters)

## Troubleshooting

If you encounter issues:

1. Check the log file (`pipeline_test.log`) for detailed error messages
2. Verify your configuration in `config/pipeline.yaml`
3. Make sure you have the required dependencies installed
4. For MusicBrainz connectivity issues, ensure you're not exceeding the rate limit (1 request per second)

## Testing Specific Components

### Testing Only Data Ingestion

To test only the data ingestion pipeline without identification:

```
python scripts/import_catalog.py data/sample_catalog.csv --db sqlite:///data/test_songwriter.db
```

### Running Unit Tests

To run the individual unit tests:

```
python -m unittest discover tests
```

Or specific test modules:

```
python -m unittest tests.test_data_ingestion
python -m unittest tests.test_musicbrainz
```
