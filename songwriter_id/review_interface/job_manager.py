"""Module for handling integration with the job scheduler."""

import os
import json
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class JobManager:
    """Manager for interacting with the job scheduler from the review interface."""
    
    def __init__(self, jobs_dir: str = None):
        """Initialize the job manager.
        
        Args:
            jobs_dir: Directory for job files
        """
        self.jobs_dir = jobs_dir or os.environ.get('JOB_SCHEDULER_DIR', 'data/jobs')
        self.jobs_path = Path(self.jobs_dir)
        self.jobs_path.mkdir(parents=True, exist_ok=True)
        
    def submit_job(self, catalog_path: str, audio_base_path: Optional[str] = None) -> str:
        """Submit a new job to the job scheduler.
        
        Args:
            catalog_path: Path to the catalog file
            audio_base_path: Base path for audio files (optional)
            
        Returns:
            Job ID
        """
        import uuid
        
        job_id = str(uuid.uuid4())
        job_file = self.jobs_path / f"{job_id}.job"
        
        job_spec = {
            'catalog_path': catalog_path,
            'audio_base_path': audio_base_path,
            'submitted_at': time.time(),
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        
        with open(job_file, 'w') as f:
            json.dump(job_spec, f)
            
        logger.info(f"Submitted job {job_id} to process catalog {catalog_path}")
        return job_id
        
    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Get the status of a job.
        
        Args:
            job_id: Job ID
            
        Returns:
            Job status information
        """
        status_file = self.jobs_path / f"{job_id}.status"
        job_file = self.jobs_path / f"{job_id}.job"
        
        # Check if job exists
        if not status_file.exists() and not job_file.exists():
            return {'status': 'not_found', 'job_id': job_id}
            
        # If job file exists but no status file, it's pending
        if job_file.exists() and not status_file.exists():
            try:
                with open(job_file, 'r') as f:
                    job_spec = json.load(f)
                    
                return {
                    'status': 'pending',
                    'job_id': job_id,
                    'submitted_at': job_spec.get('submitted_at', time.time()),
                    'created_at': job_spec.get('created_at', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
                    'catalog_path': job_spec.get('catalog_path', '')
                }
            except Exception as e:
                logger.error(f"Error reading job file {job_file}: {e}")
                return {'status': 'error', 'job_id': job_id, 'error': str(e)}
        
        # If status file exists, read it
        if status_file.exists():
            try:
                with open(status_file, 'r') as f:
                    status = json.load(f)
                    status['job_id'] = job_id
                    return status
            except Exception as e:
                logger.error(f"Error reading status file {status_file}: {e}")
                return {'status': 'error', 'job_id': job_id, 'error': str(e)}
                
        return {'status': 'unknown', 'job_id': job_id}
        
    def list_jobs(self, limit: int = None) -> List[Dict[str, Any]]:
        """List all jobs and their statuses.
        
        Args:
            limit: Optional limit on the number of jobs to return
            
        Returns:
            List of job status dictionaries
        """
        jobs = []
        
        # Get all job and status files
        job_files = list(self.jobs_path.glob('*.job'))
        status_files = list(self.jobs_path.glob('*.status'))
        
        # Process all job files
        job_ids = set()
        for job_file in job_files:
            job_id = job_file.stem
            job_ids.add(job_id)
            jobs.append(self.get_job_status(job_id))
            
        # Process status files not already covered
        for status_file in status_files:
            job_id = status_file.stem
            if job_id not in job_ids:
                jobs.append(self.get_job_status(job_id))
                
        # Sort by submitted_at (most recent first)
        jobs.sort(key=lambda x: x.get('submitted_at', 0), reverse=True)
        
        # Apply limit if specified
        if limit is not None and limit > 0:
            jobs = jobs[:limit]
                
        return jobs
