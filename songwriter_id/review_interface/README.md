# Songwriter Credits Web Interface

This directory contains the web interface for the Music Songwriter Credits Identification System. The interface provides a user-friendly way to:

1. View the status of the track identification process
2. Upload and process new music catalogs 
3. Review tracks that need manual verification
4. View detailed information about tracks and songwriter credits

## Features

### Dashboard

The dashboard provides an overview of the system status, including:
- Total tracks in the system
- Identification statistics (identified, pending, needing manual review)
- Quick links to common tasks
- List of recent tracks needing manual review

### Pipeline Interface

The pipeline interface allows you to upload and process music catalogs:
- Upload CSV or Excel files containing track information
- Optionally specify a base path to audio files
- Monitor the status of processing jobs
- View detailed statistics about completed jobs

### Track Management

The track management pages allow you to:
- Browse all tracks in the system
- Filter tracks by status (identified, pending, manual review)
- View detailed information about individual tracks
- See identification attempts and sources used

### Manual Review

The manual review interface allows you to:
- Add or edit songwriter credits for tracks
- View identification attempts and confidence scores
- Manually verify credits that couldn't be automatically identified

## Usage Guide

### Triggering the Pipeline from the Web Interface

1. Navigate to the Pipeline page by clicking "Pipeline" in the navigation bar
2. Click "Browse Files" or drag and drop a catalog file (CSV or Excel)
3. If your catalog references audio files, enter the base path to these files
4. Click "Process Catalog" to start the identification pipeline
5. You'll be redirected to the job status page where you can monitor progress
6. When processing is complete, you can see statistics and next steps

### Reviewing Tracks

1. Navigate to "Manual Review" in the navigation bar
2. Select a track to review from the list
3. View the track details, including any identification attempts
4. Click "Review" to open the editing interface
5. Add or modify songwriter credits as needed
6. Click "Save Changes" to update the track

## Configuration

The web interface uses the following environment variables (which can be set in a `.env` file):

- `SECRET_KEY`: Flask secret key for session security
- `DATABASE_URL`: Connection string for the database
- `UPLOAD_FOLDER`: Directory for storing uploaded files
- `PIPELINE_CONFIG`: Path to the pipeline configuration file

## Running the Interface

To start the web interface:

```bash
python -m songwriter_id.review_interface
```

The interface will be available at http://localhost:5000.

For production deployment, it's recommended to use a proper WSGI server like Gunicorn or uWSGI with a reverse proxy like Nginx.

## Project Structure

```
review_interface/
├── __init__.py          # Package initialization and app creation
├── app.py               # Main Flask application definition
├── static/              # Static assets (CSS, JS, images)
├── templates/           # HTML templates
│   ├── index.html       # Dashboard template
│   ├── tracks.html      # Track listing template
│   ├── track_detail.html # Individual track view
│   ├── review_track.html # Manual review interface
│   ├── pipeline.html    # Pipeline upload interface
│   └── job_status.html  # Pipeline job status page
└── README.md            # This documentation
```

## Background Processing

The pipeline processing happens in a background thread, allowing the user to continue using the interface while catalogs are being processed. Job status is updated in real-time and can be monitored through the job status page.

The job status page automatically refreshes when a job is in progress, providing updates as the pipeline processes the catalog through the various tiers of identification.

## Security Considerations

- File uploads are secured with size limits and filename sanitization
- Database operations use SQLAlchemy's ORM to prevent SQL injection
- Sensitive configuration is managed through environment variables
- For production, ensure proper file permissions on the uploads directory

## Troubleshooting

### Common Issues

1. **Job status not updating**: Check that the background thread is running and has permissions to write to the jobs directory.

2. **Upload errors**: Verify that the upload directory exists and is writable by the web server process.

3. **Database connection errors**: Confirm that the database connection string is correct and the database is accessible.

4. **Pipeline configuration issues**: Ensure the pipeline configuration file exists and is properly formatted.

### Logs

The web interface logs to the standard Flask logger. Check the logs for detailed error information and troubleshooting hints.
