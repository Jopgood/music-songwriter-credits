"""Job scheduler for processing catalog jobs in the background."""

import os
import threading
import time
import logging
import json
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class JobScheduler:
    """Simple job scheduler for processing catalogs in the background."""
    
    def __init__(self, pipeline, jobs_dir: str = 'data/jobs'):
        """Initialize the job scheduler.
        
        Args:
            pipeline: Initialized SongwriterIdentificationPipeline
            jobs_dir: Directory for job files
        """
        self.pipeline = pipeline
        self.jobs_dir = Path(jobs_dir)
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.active_jobs = {}
        self.polling_thread = None
        self.running = False
        
    def start(self):
        """Start the job scheduler."""
        if self.polling_thread and self.polling_thread.is_alive():
            logger.warning("Job scheduler already running")
            return
            
        self.running = True
        self.polling_thread = threading.Thread(target=self._polling_loop)
        self.polling_thread.daemon = True
        self.polling_thread.start()
        logger.info("Job scheduler started")
        
    def stop(self):
        """Stop the job scheduler."""
        self.running = False
        if self.polling_thread:
            self.polling_thread.join(timeout=5)
        logger.info("Job scheduler stopped")
        
    def submit_job(self, catalog_path: str, audio_base_path: Optional[str] = None) -> str:
        """Submit a new job to process a catalog.
        
        Args:
            catalog_path: Path to the catalog file
            audio_base_path: Base path for audio files (optional)
            
        Returns:
            Job ID
        """
        import uuid
        
        job_id = str(uuid.uuid4())
        job_file = self.jobs_dir / f"{job_id}.job"
        
        job_spec = {
            'catalog_path': catalog_path,
            'audio_base_path': audio_base_path,
            'submitted_at': time.time()
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
        status_file = self.jobs_dir / f"{job_id}.status"
        job_file = self.jobs_dir / f"{job_id}.job"
        
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
        
    def list_jobs(self) -> Dict[str, Dict[str, Any]]:
        """List all jobs and their statuses.
        
        Returns:
            Dictionary of job IDs and their statuses
        """
        jobs = {}
        
        # Get all job and status files
        job_files = list(self.jobs_dir.glob('*.job'))
        status_files = list(self.jobs_dir.glob('*.status'))
        
        # Process pending jobs
        for job_file in job_files:
            job_id = job_file.stem
            jobs[job_id] = self.get_job_status(job_id)
            
        # Process jobs with status
        for status_file in status_files:
            job_id = status_file.stem
            if job_id not in jobs:
                jobs[job_id] = self.get_job_status(job_id)
                
        return jobs
        
    def _polling_loop(self):
        """Main polling loop to check for new jobs."""
        while self.running:
            # Look for job files
            job_files = list(self.jobs_dir.glob('*.job'))
            
            for job_file in job_files:
                try:
                    # Load job specification
                    with open(job_file, 'r') as f:
                        job_spec = json.load(f)
                        
                    # Create status file to mark job as in progress
                    job_id = job_file.stem
                    status_file = job_file.with_suffix('.status')
                    with open(status_file, 'w') as f:
                        json.dump({
                            'status': 'running',
                            'start_time': time.time()
                        }, f)
                        
                    # Remove job file to prevent reprocessing
                    job_file.unlink()
                    
                    # Process the job
                    self._process_job(job_id, job_spec, status_file)
                    
                except Exception as e:
                    logger.error(f"Error processing job file {job_file}: {e}")
                    
            # Sleep before next check
            time.sleep(5)
            
    def _process_job(self, job_id: str, job_spec: Dict[str, Any], status_file: Path):
        """Process a single job.
        
        Args:
            job_id: Job ID
            job_spec: Job specification
            status_file: Path to the status file
        """
        logger.info(f"Processing job {job_id}")
        
        try:
            # Extract job parameters
            catalog_path = job_spec.get('catalog_path')
            audio_base_path = job_spec.get('audio_base_path')
            
            if not catalog_path or not os.path.exists(catalog_path):
                raise ValueError(f"Invalid catalog path: {catalog_path}")
                
            # Process the catalog
            result = self.pipeline.process_catalog(
                catalog_path=catalog_path,
                audio_base_path=audio_base_path
            )
            
            # Update status file with result
            with open(status_file, 'w') as f:
                json.dump({
                    'status': 'completed',
                    'result': result,
                    'end_time': time.time()
                }, f)
                
            logger.info(f"Job {job_id} completed successfully")
            
        except Exception as e:
            logger.error(f"Error processing job {job_id}: {e}")
            
            # Update status file with error
            with open(status_file, 'w') as f:
                json.dump({
                    'status': 'failed',
                    'error': str(e),
                    'end_time': time.time()
                }, f)
