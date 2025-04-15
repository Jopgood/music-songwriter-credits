# Job Scheduler

This document explains the Job Scheduler system that has been implemented to make the Music Songwriter Credits Identification System run as a long-lived service rather than a one-time batch process.

## Overview

The Job Scheduler is a background process that continually monitors a directory for job specification files. When a new job is detected, it processes the catalog file specified in the job and updates a status file with the results.

## Components

### 1. Main App Daemon Mode

The main application now supports a daemon mode with the `--daemon` flag:

```bash
python -m songwriter_id --daemon --jobs-dir=/path/to/jobs
```

When started in daemon mode, the application:
- Initializes all components (database, API clients, etc.)
- Starts a job scheduler that monitors the jobs directory
- Stays running indefinitely, processing jobs as they appear

### 2. Job Scheduler

The `JobScheduler` class in `songwriter_id/scheduler.py` is responsible for:
- Monitoring the jobs directory for new job files
- Processing jobs in the background
- Updating status files with job progress and results

### 3. Review Interface Integration

The web interface has been updated to integrate with the job scheduler:
- The `JobManager` class in `songwriter_id/review_interface/job_manager.py` provides an interface to the job scheduler
- The upload form now creates job specification files instead of directly running the pipeline
- Job status pages now read from the status files created by the job scheduler

## How It Works

### Job Submission Flow

1. A user uploads a catalog file through the web interface
2. The web interface saves the uploaded file and creates a job specification file (*.job) in the jobs directory
3. The job scheduler (running in the app container) detects the new job file
4. The scheduler processes the job and updates a status file (*.status) with progress and results
5. The web interface monitors the status file to display job progress to the user

### Job File Format

Job specification files (*.job) are JSON files with the following structure:

```json
{
  "catalog_path": "/path/to/catalog.csv",
  "audio_base_path": "/optional/audio/path",
  "submitted_at": 1618514000.123
}
```

### Status File Format

Status files (*.status) are JSON files with the following structure:

```json
{
  "status": "running|completed|failed",
  "start_time": 1618514010.456,
  "end_time": 1618514020.789,
  "result": {
    "import": { /* import statistics */ },
    "identification": { /* identification statistics */ }
  }
}
```

## Directory Structure

The system uses the following directory structure:

```
data/
  jobs/          # Job and status files
    {job_id}.job      # Job specification
    {job_id}.status   # Job status and results
uploads/
  catalogs/      # Uploaded catalog files
```

## Configuration

The job scheduler can be configured with:

1. **Docker Compose**: The environment variables in docker-compose.yml
2. **Command Line**: The `--jobs-dir` flag when running in daemon mode
3. **Environment Variables**: Set JOB_SCHEDULER_DIR for the review interface

## Benefits

This job scheduling system provides several benefits:

1. **Long-Running Service**: The app now stays alive and processes jobs continuously
2. **Resilience**: Jobs are persisted as files, so they survive application restarts
3. **Status Tracking**: Jobs provide detailed status information
4. **Separation of Concerns**: The web interface submits jobs but doesn't process them directly

## Implementation Details

- The scheduler runs in a background thread within the main app process
- It polls the jobs directory every few seconds for new job files
- When a job is processed, the job file is deleted and a status file is created
- Both containers (app and review-ui) share the jobs directory through a volume mount
