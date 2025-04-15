"""Flask application for the manual review interface."""

import os
import uuid
import json
from datetime import datetime
from typing import Dict, List, Optional
from werkzeug.utils import secure_filename

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy

# Import database models
from songwriter_id.database.models import Base, Track, SongwriterCredit, IdentificationAttempt
# Import pipeline for processing catalogs
from songwriter_id.pipeline import SongwriterIdentificationPipeline

# Create the database instance
db = SQLAlchemy(model_class=Base)


def create_app():
    """Create and configure the Flask application.

    Returns:
        Configured Flask application
    """
    app = Flask(__name__, 
                template_folder=os.path.join(os.path.dirname(__file__), 'templates'),
                static_folder=os.path.join(os.path.dirname(__file__), 'static'))
    
    # Configure the app
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev_key_change_in_production')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
        'DATABASE_URL', 'postgresql://songwriter:password@localhost:5432/songwriter_db'
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['UPLOAD_FOLDER'] = os.environ.get('UPLOAD_FOLDER', 'uploads')
    app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max upload size
    app.config['PIPELINE_CONFIG'] = os.environ.get('PIPELINE_CONFIG', 'config/pipeline.yaml')
    
    # Ensure upload directory exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Initialize the database with the app
    db.init_app(app)
    
    # Register routes
    @app.route('/')
    def index():
        """Dashboard homepage."""
        # Get summary statistics
        stats = {}
        with app.app_context():
            try:
                stats['total_tracks'] = db.session.query(Track).count()
                stats['pending_tracks'] = db.session.query(Track).filter_by(identification_status='pending').count()
                stats['identified_tracks'] = db.session.query(Track).filter_by(identification_status='identified').count()
                stats['manual_review_tracks'] = db.session.query(Track).filter_by(identification_status='manual_review').count()
                
                # Get recent tracks for manual review
                recent_tracks = db.session.query(Track)\
                    .filter_by(identification_status='manual_review')\
                    .order_by(Track.updated_at.desc())\
                    .limit(10)
                
                return render_template('index.html', stats=stats, recent_tracks=recent_tracks)
            except Exception as e:
                # For debugging: return a simple message with error details
                return f"Database connection error: {str(e)}"
    
    @app.route('/tracks')
    def list_tracks():
        """List all tracks."""
        # Get filter parameters
        status = request.args.get('status', 'all')
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        
        # Query tracks with filtering
        query = db.session.query(Track)
        if status != 'all':
            query = query.filter_by(identification_status=status)
            
        tracks = query.order_by(Track.updated_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        return render_template('tracks.html', tracks=tracks, status=status)
    
    @app.route('/tracks/<int:track_id>')
    def track_detail(track_id):
        """Show track details."""
        track = db.session.query(Track).get_or_404(track_id)
        credits = db.session.query(SongwriterCredit).filter_by(track_id=track_id).all()
        attempts = db.session.query(IdentificationAttempt).filter_by(track_id=track_id).all()
        
        return render_template('track_detail.html', track=track, credits=credits, attempts=attempts)
    
    @app.route('/tracks/<int:track_id>/review', methods=['GET', 'POST'])
    def review_track(track_id):
        """Review a track's songwriter credits."""
        track = db.session.query(Track).get_or_404(track_id)
        
        if request.method == 'POST':
            # Process form submission for updating credits
            try:
                # Clear existing credits
                db.session.query(SongwriterCredit).filter_by(track_id=track_id).delete()
                
                # Add new credits from form
                songwriter_count = int(request.form.get('songwriter_count', 0))
                for i in range(songwriter_count):
                    if request.form.get(f'songwriter_name_{i}'):
                        credit = SongwriterCredit(
                            track_id=track_id,
                            songwriter_name=request.form.get(f'songwriter_name_{i}'),
                            role=request.form.get(f'role_{i}'),
                            share_percentage=float(request.form.get(f'share_percentage_{i}', 0)),
                            publisher_name=request.form.get(f'publisher_name_{i}'),
                            source_of_info='manual_review',
                            confidence_score=1.0  # Manual review is highest confidence
                        )
                        db.session.add(credit)
                
                # Update track status
                track.identification_status = 'identified'
                track.confidence_score = 1.0
                track.updated_at = datetime.now()
                
                db.session.commit()
                flash('Track credits updated successfully.', 'success')
                return redirect(url_for('track_detail', track_id=track_id))
            except Exception as e:
                db.session.rollback()
                flash(f'Error updating track credits: {str(e)}', 'error')
        
        # Get existing credits and attempts for the track
        credits = db.session.query(SongwriterCredit).filter_by(track_id=track_id).all()
        attempts = db.session.query(IdentificationAttempt).filter_by(track_id=track_id).all()
        
        return render_template('review_track.html', track=track, credits=credits, attempts=attempts)
    
    @app.route('/api/tracks/<int:track_id>/credits', methods=['GET'])
    def api_track_credits(track_id):
        """API endpoint for track credits."""
        credits = db.session.query(SongwriterCredit).filter_by(track_id=track_id).all()
        result = [
            {
                'credit_id': c.credit_id,
                'songwriter_name': c.songwriter_name,
                'role': c.role,
                'share_percentage': c.share_percentage,
                'publisher_name': c.publisher_name,
                'source_of_info': c.source_of_info,
                'confidence_score': c.confidence_score
            }
            for c in credits
        ]
        
        return jsonify(result)
    
    @app.route('/api/health', methods=['GET'])
    def health_check():
        """API endpoint for health check."""
        return jsonify({"status": "ok", "message": "Service is running"})
    
    # New routes for pipeline interface
    @app.route('/pipeline', methods=['GET'])
    def pipeline_interface():
        """Show pipeline interface for uploading and processing catalogs."""
        # Get recent pipeline jobs
        job_files = []
        jobs_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'jobs')
        if os.path.exists(jobs_dir):
            for job_file in os.listdir(jobs_dir):
                if job_file.endswith('.json'):
                    job_path = os.path.join(jobs_dir, job_file)
                    try:
                        with open(job_path, 'r') as f:
                            job_data = json.load(f)
                            job_files.append(job_data)
                    except Exception as e:
                        continue
        
        # Sort by timestamp (newest first)
        job_files.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
        
        return render_template('pipeline.html', jobs=job_files[:10])  # Show last 10 jobs
    
    @app.route('/pipeline/upload', methods=['POST'])
    def upload_catalog():
        """Handle catalog file upload and start the pipeline."""
        if 'catalog_file' not in request.files:
            flash('No file part', 'error')
            return redirect(url_for('pipeline_interface'))
        
        file = request.files['catalog_file']
        if file.filename == '':
            flash('No selected file', 'error')
            return redirect(url_for('pipeline_interface'))
        
        if file:
            # Generate a unique job ID
            job_id = str(uuid.uuid4())
            
            # Generate unique filename
            filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            unique_filename = f"{timestamp}_{filename}"
            
            # Create uploads and jobs directories if they don't exist
            uploads_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'catalogs')
            jobs_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'jobs')
            os.makedirs(uploads_dir, exist_ok=True)
            os.makedirs(jobs_dir, exist_ok=True)
            
            # Save the uploaded file
            file_path = os.path.join(uploads_dir, unique_filename)
            file.save(file_path)
            
            # Get audio base path if provided
            audio_base_path = request.form.get('audio_base_path', '')
            
            # Save job info
            job_info = {
                'job_id': job_id,
                'catalog_file': unique_filename,
                'catalog_path': file_path,
                'audio_base_path': audio_base_path,
                'status': 'pending',
                'timestamp': datetime.now().timestamp(),
                'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'stats': {}
            }
            
            # Save job info to file
            job_file_path = os.path.join(jobs_dir, f"{job_id}.json")
            with open(job_file_path, 'w') as f:
                json.dump(job_info, f)
            
            # Start pipeline processing in a background thread
            import threading
            thread = threading.Thread(
                target=process_catalog_job,
                args=(app, job_id, file_path, audio_base_path, job_file_path)
            )
            thread.daemon = True
            thread.start()
            
            flash(f'Catalog file uploaded successfully. Job ID: {job_id}', 'success')
            return redirect(url_for('pipeline_job_status', job_id=job_id))
        
        return redirect(url_for('pipeline_interface'))
    
    @app.route('/pipeline/jobs/<job_id>', methods=['GET'])
    def pipeline_job_status(job_id):
        """Show status of a pipeline job."""
        job_file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'jobs', f"{job_id}.json")
        
        if not os.path.exists(job_file_path):
            flash('Job not found', 'error')
            return redirect(url_for('pipeline_interface'))
        
        try:
            with open(job_file_path, 'r') as f:
                job_info = json.load(f)
                
            return render_template('job_status.html', job=job_info)
        except Exception as e:
            flash(f'Error loading job information: {str(e)}', 'error')
            return redirect(url_for('pipeline_interface'))
    
    @app.route('/pipeline/jobs/<job_id>/json', methods=['GET'])
    def pipeline_job_json(job_id):
        """Return job status as JSON."""
        job_file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'jobs', f"{job_id}.json")
        
        if not os.path.exists(job_file_path):
            return jsonify({'error': 'Job not found'}), 404
        
        try:
            with open(job_file_path, 'r') as f:
                job_info = json.load(f)
                
            return jsonify(job_info)
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    @app.route('/uploads/<path:filename>')
    def download_file(filename):
        """Serve uploaded files."""
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
    
    return app


def process_catalog_job(app, job_id, catalog_path, audio_base_path, job_file_path):
    """Process a catalog file in the background.
    
    Args:
        app: Flask application context
        job_id: Unique job ID
        catalog_path: Path to the catalog file
        audio_base_path: Base path for audio files
        job_file_path: Path to the job status file
    """
    # Update job status to 'processing'
    update_job_status(job_file_path, 'processing')
    
    try:
        # Initialize the pipeline with app context
        with app.app_context():
            pipeline = SongwriterIdentificationPipeline(
                config_file=app.config['PIPELINE_CONFIG'],
                db_connection=app.config['SQLALCHEMY_DATABASE_URI']
            )
            
            # Process the catalog
            stats = pipeline.process_catalog(
                catalog_path=catalog_path,
                audio_base_path=audio_base_path
            )
            
            # Update job status to 'completed' with stats
            update_job_status(job_file_path, 'completed', stats)
            
    except Exception as e:
        # Update job status to 'failed'
        update_job_status(job_file_path, 'failed', {'error': str(e)})


def update_job_status(job_file_path, status, stats=None):
    """Update the status of a pipeline job.
    
    Args:
        job_file_path: Path to the job status file
        status: New status ('pending', 'processing', 'completed', 'failed')
        stats: Statistics to include in the job info
    """
    try:
        # Read current job info
        with open(job_file_path, 'r') as f:
            job_info = json.load(f)
        
        # Update status and stats
        job_info['status'] = status
        job_info['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        if stats:
            job_info['stats'] = stats
        
        # Save updated job info
        with open(job_file_path, 'w') as f:
            json.dump(job_info, f)
            
    except Exception as e:
        # Log error but don't raise
        print(f"Error updating job status: {e}")
