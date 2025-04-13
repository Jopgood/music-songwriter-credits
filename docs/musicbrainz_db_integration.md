# MusicBrainz Database Integration

This document provides information about the direct MusicBrainz database integration with the Songwriter Credits Identification System.

## Overview

The system can now connect directly to a MusicBrainz database running in Docker or elsewhere, allowing for faster and more flexible querying compared to using the MusicBrainz API. The benefits include:

- **No rate limiting**: Direct database access isn't restricted by MusicBrainz API rate limits
- **Faster queries**: Local database queries are much faster than API calls over the network
- **Complex queries**: Direct SQL allows for more sophisticated queries than what's possible through the API
- **Better batch processing**: Can process multiple tracks simultaneously with custom indexing

## Configuration

To use the MusicBrainz database integration, update your `config/pipeline.yaml` file:

```yaml
apis:
  musicbrainz:
    enabled: true
    client_type: "database"  # Set to "database" instead of "api"
    
    # Database client settings 
    database:
      enabled: true
      connection_string: "postgresql://musicbrainz:musicbrainz@localhost:5432/musicbrainz"
      pool_size: 10
      max_overflow: 20
```

### Configuration Options

- `client_type`: Choose between "api" or "database"
- `database.connection_string`: PostgreSQL connection string for your MusicBrainz database
- `database.pool_size`: Size of the connection pool (default: 5)
- `database.max_overflow`: Maximum overflow connections (default: 10)

## Setup with Docker

If you have a Docker-based MusicBrainz database, the integration should work automatically with the appropriate connection string. The system will use SQLAlchemy to connect to the database.

### Example Docker Connection String

```
postgresql://musicbrainz:musicbrainz@docker-host:5432/musicbrainz
```

Replace `docker-host` with the hostname or IP address where your Docker container is running.

## SQL Queries

The implementation uses the following SQL queries to extract songwriter information:

### Finding works based on recording name and artist

```sql
SELECT
    w.id AS work_id,
    w.name AS work_name,
    r.id AS recording_id,
    r.name AS recording_name,
    a.id AS artist_id,
    a.name AS artist_name
FROM
    recording r
JOIN
    l_recording_work lrw ON r.id = lrw.entity0
JOIN
    work w ON w.id = lrw.entity1
JOIN
    artist_credit ac ON r.artist_credit = ac.id
JOIN
    artist_credit_name acn ON acn.artist_credit = ac.id
JOIN
    artist a ON a.id = acn.artist
WHERE
    LOWER(r.name) LIKE LOWER(:title)
AND
    LOWER(a.name) LIKE LOWER(:artist)
```

### Retrieving Composers and Publishers

```sql
WITH recording_work AS (
    SELECT
        w.id AS work_id
    FROM
        recording r
    JOIN
        l_recording_work lrw ON r.id = lrw.entity0
    JOIN
        work w ON w.id = lrw.entity1
    WHERE
        r.id = :recording_id
)
-- Get composers and lyricists
SELECT
    'composer/lyricist' AS contributor_type,
    a.name AS contributor_name,
    lt.name AS role
FROM
    recording_work rw
JOIN
    l_artist_work law ON rw.work_id = law.entity1
JOIN
    artist a ON a.id = law.entity0
JOIN
    link l ON law.link = l.id
JOIN
    link_type lt ON l.link_type = lt.id
WHERE
    lt.name IN ('composer', 'songwriter', 'lyricist', 'writer')

UNION ALL

-- Get publishers
SELECT
    'publisher' AS contributor_type,
    p.name AS contributor_name,
    lt.name AS role
FROM
    recording_work rw
JOIN
    l_label_work llw ON rw.work_id = llw.entity1
JOIN
    label p ON p.id = llw.entity0
JOIN
    link l ON llw.link = l.id
JOIN
    link_type lt ON l.link_type = lt.id
WHERE
    lt.name IN ('publisher', 'publishing')
```

## Fallback Mechanism

The system is designed to fall back to the MusicBrainz API client if:

1. The database client is not available (e.g., missing database connection)
2. The `client_type` is set to "api" in the configuration
3. An error occurs when connecting to the database

This ensures the system can still function even without direct database access.

## Performance Considerations

### Connection Pooling

The database client uses SQLAlchemy's connection pooling to maintain an efficient set of database connections. This reduces the overhead of creating and closing connections for each query.

### Query Optimization

The SQL queries have been optimized to:
- Use appropriate joins to minimize data retrieval
- Apply filters early in the query execution
- Implement proper indexing strategies

### Batch Processing

For optimal performance when processing large catalogs, consider increasing the `batch_size` parameter in the configuration.

## Troubleshooting

### Connection Issues

If you encounter connection issues, verify:
- The Docker container is running and accessible
- The connection string is correct
- The user has appropriate permissions

### Missing Data

If you're not getting expected results:
- Check if the MusicBrainz database is fully populated
- Verify the database schema matches the expected structure
- Look at the debug logs for SQL query details

## Dependencies

This integration requires:
- SQLAlchemy
- PostgreSQL driver (psycopg2)

Make sure these are installed in your environment:

```bash
pip install sqlalchemy psycopg2-binary
```
