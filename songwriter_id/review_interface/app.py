"""Flask application for the manual review interface."""

import os
import uuid
import json
import yaml
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from werkzeug.utils import secure_filename

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy

# Import database models and utilities
from songwriter_id.database.models import Base, Track, SongwriterCredit, IdentificationAttempt
from songwriter_id.database.setup import test_connection
from songwriter_id.database.connection import check_all_connections

# Import Job Manager for the scheduler integration
from songwriter_id.review_interface.job_manager import JobManager

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
    app.config['JOB_SCHEDULER_DIR'] = os.environ.get('JOB_SCHEDULER_DIR', 'data/jobs')
    
    # Initialize job manager
    app.config['job_manager'] = JobManager(jobs_dir=app.config['JOB_SCHEDULER_DIR'])
    
    # Ensure upload directory exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'catalogs'), exist_ok=True)
    
    # Initialize the database with the app
    db.init_app(app)
    
    # Test database connection
    with app.app_context():
        db_success, db_error = test_connection(app.config['SQLALCHEMY_DATABASE_URI'])
        
        # Load configuration to check other connections
        config_path = app.config['PIPELINE_CONFIG']
        config = {}
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    config = yaml.safe_load(f) or {}
            except Exception as e:
                app.logger.error(f"Error loading config file: {e}")
        
        # Store connection status in app context for templates to access
        app.config['CONNECTION_STATUS'] = {
            'main_database': (db_success, db_error),
        }
        
        # Check MusicBrainz connection if configured
        mb_config = config.get('apis', {}).get('musicbrainz', {})
        if mb_config.get('enabled', False) and mb_config.get('client_type') == 'database':
            db_config = mb_config.get('database', {})
            mb_connection = db_config.get('connection_string')
            if mb_connection:
                mb_success, mb_error = test_connection(mb_connection)
                app.config['CONNECTION_STATUS']['musicbrainz_database'] = (mb_success, mb_error)
    
    # Register routes
    @app.route('/')
    def index():
        """Dashboard homepage."""
        # Get summary statistics
        stats = {}
        connections = app.config.get('CONNECTION_STATUS', {})
        db_success = connections.get('main_database', (False, "Unknown"))[0]
        
        if not db_success:
            error_msg = connections.get('main_database', (False, "Unknown connection error"))[1]
            flash(f"Database connection error: {error_msg}", "danger")
            return render_template('error.html', 
                               title="Database Connection Error", 
                               message=f"Could not connect to the database. Please check your connection settings.",
                               details=error_msg,
                               connections=connections)
        
        try:
            stats['total_tracks'] = db.session.query(Track).count()
            stats['pending_tracks'] = db.session.query(Track).filter_by(identification_status='pending').count()
            
            # Include all identified statuses
            identified_statuses = ['identified', 'identified_tier1', 'identified_tier2', 'identified_tier3']
            stats['identified_tracks'] = db.session.query(Track).filter(
                Track.identification_status.in_(identified_statuses)
            ).count()
            
            stats['manual_review_tracks'] = db.session.query(Track).filter_by(identification_status='manual_review').count()
            
            # Get recent tracks for manual review
            recent_tracks = db.session.query(Track)\
                .filter_by(identification_status='manual_review')\
                .order_by(Track.updated_at.desc())\
                .limit(10)
            
            # Get recent jobs using the job manager
            job_manager = app.config['job_manager']
            recent_jobs = job_manager.list_jobs(limit=5)
            
            return render_template('index.html', 
                                stats=stats, 
                                recent_tracks=recent_tracks,
                                recent_jobs=recent_jobs,
                                connections=connections)
                
        except Exception as e:
            # For debugging: return a simple message with error details
            app.logger.error(f"Database error: {str(e)}")
            return render_template('error.html', 
                                title="Database Error", 
                                message="An error occurred while accessing the database.",
                                details=str(e),
                                connections=connections)
    
    @app.route('/tracks')
    def list_tracks():
        """List all tracks."""
        connections = app.config.get('CONNECTION_STATUS', {})
        db_success = connections.get('main_database', (False, "Unknown"))[0]
        
        if not db_success:
            error_msg = connections.get('main_database', (False, "Unknown connection error"))[1]
            flash(f"Database connection error: {error_msg}", "danger")
            return render_template('error.html', 
                               title="Database Connection Error", 
                               message="Could not connect to the database. Please check your connection settings.",
                               details=error_msg,
                               connections=connections)
        
        try:
            # Get filter parameters
            status = request.args.get('status', 'all')
            page = request.args.get('page', 1, type=int)
            per_page = request.args.get('per_page', 50, type=int)
            
            # Query tracks with filtering
            query = db.session.query(Track)
            if status != 'all':
                if status == 'identified':
                    # Include all identified statuses
                    identified_statuses = ['identified', 'identified_tier1', 'identified_tier2', 'identified_tier3']
                    query = query.filter(Track.identification_status.in_(identified_statuses))
                else:
                    query = query.filter_by(identification_status=status)
                
            tracks = query.order_by(Track.updated_at.desc()).paginate(
                page=page, per_page=per_page, error_out=False
            )
            
            return render_template('tracks.html', 
                                tracks=tracks, 
                                status=status, 
                                connections=connections)
                                
        except Exception as e:
            flash(f"Database error: {str(e)}", "danger")
            return render_template('error.html', 
                               title="Database Error", 
                               message="An error occurred while querying tracks.",
                               details=str(e),
                               connections=connections)
    
    @app.route('/tracks/<int:track_id>')
    def track_detail(track_id):
        """Show track details."""
        connections = app.config.get('CONNECTION_STATUS', {})
        db_success = connections.get('main_database', (False, "Unknown"))[0]
        
        if not db_success:
            flash("Database connection error", "danger")
            return redirect(url_for('index'))
        
        try:
            track = db.session.query(Track).get_or_404(track_id)
            credits = db.session.query(SongwriterCredit).filter_by(track_id=track_id).all()
            attempts = db.session.query(IdentificationAttempt).filter_by(track_id=track_id).all()
            
            return render_template('track_detail.html', 
                                track=track, 
                                credits=credits, 
                                attempts=attempts,
                                connections=connections)
        except Exception as e:
            flash(f"Error retrieving track details: {str(e)}", "danger")
            return redirect(url_for('index'))
    
    @app.route('/tracks/<int:track_id>/review', methods=['GET', 'POST'])
    def review_track(track_id):
        """Review a track's songwriter credits."""
        connections = app.config.get('CONNECTION_STATUS', {})
        db_success = connections.get('main_database', (False, "Unknown"))[0]
        
        if not db_success:
            flash("Database connection error", "danger")
            return redirect(url_for('index'))
            
        try:
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
            
            return render_template('review_track.html', 
                                track=track, 
                                credits=credits, 
                                attempts=attempts,
                                connections=connections)
        except Exception as e:
            flash(f"Error retrieving track: {str(e)}", "danger")
            return redirect(url_for('index'))
    
    @app.route('/api/tracks/<int:track_id>/credits', methods=['GET'])
    def api_track_credits(track_id):
        """API endpoint for track credits."""
        try:
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
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    @app.route('/api/health', methods=['GET'])
    def health_check():
        """API endpoint for health check."""
        connections = app.config.get('CONNECTION_STATUS', {})
        db_success = connections.get('main_database', (False, "Unknown"))[0]
        mb_success = connections.get('musicbrainz_database', (True, None))[0]  # Default to True if not configured
        
        status = "ok" if db_success else "error"
        return jsonify({
            "status": status,
            "connections": {
                "database": "connected" if db_success else "disconnected",
                "musicbrainz": "connected" if mb_success else "disconnected"
            },
            "message": "Service is running"
        })
    
    @app.route('/system/status', methods=['GET'])
    def system_status():
        """View system status."""
        connections = app.config.get('CONNECTION_STATUS', {})
        
        # Check connections again when this endpoint is hit
        with app.app_context():
            db_success, db_error = test_connection(app.config['SQLALCHEMY_DATABASE_URI'])
            app.config['CONNECTION_STATUS']['main_database'] = (db_success, db_error)
            
            # Check MusicBrainz connection if configured
            config_path = app.config['PIPELINE_CONFIG']
            if os.path.exists(config_path):
                try:
                    with open(config_path, 'r') as f:
                        config = yaml.safe_load(f) or {}
                        
                    mb_config = config.get('apis', {}).get('musicbrainz', {})
                    if mb_config.get('enabled', False) and mb_config.get('client_type') == 'database':
                        db_config = mb_config.get('database', {})
                        mb_connection = db_config.get('connection_string')
                        if mb_connection:
                            mb_success, mb_error = test_connection(mb_connection)
                            app.config['CONNECTION_STATUS']['musicbrainz_database'] = (mb_success, mb_error)
                except Exception as e:
                    app.logger.error(f"Error checking connections: {e}")
        
        connections = app.config.get('CONNECTION_STATUS', {})
        
        # Get disk space info for uploads folder
        upload_stats = {}
        try:
            uploads_path = app.config['UPLOAD_FOLDER']
            total_size = 0
            file_count = 0
            
            for dirpath, dirnames, filenames in os.walk(uploads_path):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    if os.path.exists(fp) and os.path.isfile(fp):
                        total_size += os.path.getsize(fp)
                        file_count += 1
            
            upload_stats = {
                'size_mb': round(total_size / (1024 * 1024), 2),
                'file_count': file_count
            }
        except Exception as e:
            app.logger.error(f"Error getting disk space info: {e}")
            upload_stats = {'error': str(e)}
        
        # Get job scheduler directory info
        job_stats = {}
        try:
            job_manager = app.config['job_manager']
            jobs = job_manager.list_jobs()
            
            # Categorize jobs by status
            status_counts = {}
            for job in jobs:
                status = job.get('status', 'unknown')
                status_counts[status] = status_counts.get(status, 0) + 1
            
            job_stats = {
                'total_jobs': len(jobs),
                'status_counts': status_counts
            }
        except Exception as e:
            app.logger.error(f"Error getting job stats: {e}")
            job_stats = {'error': str(e)}
        
        return render_template('system_status.html', 
                              connections=connections,
                              config_path=app.config['PIPELINE_CONFIG'],
                              upload_stats=upload_stats,
                              job_stats=job_stats)
    
    # New routes for pipeline interface
    @app.route('/pipeline', methods=['GET'])
    def pipeline_interface():
        """Show pipeline interface for uploading and processing catalogs."""
        connections = app.config.get('CONNECTION_STATUS', {})
        db_success = connections.get('main_database', (False, "Unknown"))[0]
        
        if not db_success:
            flash("Database connection error. The pipeline cannot operate without database access.", "danger")
            return render_template('error.html', 
                               title="Database Connection Error", 
                               message="The pipeline requires database access to function.",
                               details=connections.get('main_database', (False, "Unknown"))[1],
                               connections=connections)
        
        # Get jobs using the job manager
        job_manager = app.config['job_manager']
        jobs = job_manager.list_jobs()
        
        return render_template('pipeline.html', 
                              jobs=jobs, 
                              connections=connections)
    
    @app.route('/pipeline/upload', methods=['POST'])
    def upload_catalog():
        """Handle catalog file upload and start the pipeline."""
        connections = app.config.get('CONNECTION_STATUS', {})
        db_success = connections.get('main_database', (False, "Unknown"))[0]
        
        if not db_success:
            flash("Database connection error. Cannot process catalog without database access.", "danger")
            return redirect(url_for('pipeline_interface'))
        
        if 'catalog_file' not in request.files:
            flash('No file part', 'error')
            return redirect(url_for('pipeline_interface'))
        
        file = request.files['catalog_file']
        if file.filename == '':
            flash('No selected file', 'error')
            return redirect(url_for('pipeline_interface'))
        
        if file:
            try:
                # Generate unique filename
                filename = file.filename.replace(' ', '_')
                safe_filename = ''.join(c for c in filename if c.isalnum() or c in '._-')
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                unique_filename = f"{timestamp}_{safe_filename}"
                
                # Create uploads directory if it doesn't exist
                uploads_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'catalogs')
                os.makedirs(uploads_dir, exist_ok=True)
                
                # Save the uploaded file
                file_path = os.path.join(uploads_dir, unique_filename)
                file.save(file_path)
                
                # Get audio base path if provided
                audio_base_path = request.form.get('audio_base_path', '')
                
                # Submit job to the scheduler using job manager
                job_manager = app.config['job_manager']
                job_id = job_manager.submit_job(
                    catalog_path=file_path,
                    audio_base_path=audio_base_path
                )
                
                flash(f'Catalog file uploaded successfully and submitted to the job scheduler. Job ID: {job_id}', 'success')
                return redirect(url_for('pipeline_job_status', job_id=job_id))
            
            except Exception as e:
                app.logger.error(f"Error uploading file: {e}")
                flash(f'Error uploading file: {str(e)}', 'danger')
        
        return redirect(url_for('pipeline_interface'))
    
    @app.route('/pipeline/jobs/<job_id>', methods=['GET'])
    def pipeline_job_status(job_id):
        """Show status of a pipeline job."""
        connections = app.config.get('CONNECTION_STATUS', {})
        job_manager = app.config['job_manager']
        
        # Get job status from the job manager
        job_info = job_manager.get_job_status(job_id)
        
        if job_info.get('status') == 'not_found':
            flash('Job not found', 'error')
            return redirect(url_for('pipeline_interface'))
        
        # Add auto-refresh for running or pending jobs
        auto_refresh = job_info.get('status') in ['running', 'pending']
        
        return render_template('job_status.html', 
                            job=job_info,
                            connections=connections,
                            auto_refresh=auto_refresh)
    
    @app.route('/pipeline/jobs/<job_id>/json', methods=['GET'])
    def pipeline_job_json(job_id):
        """Return job status as JSON."""
        job_manager = app.config['job_manager']
        job_info = job_manager.get_job_status(job_id)
        
        if job_info.get('status') == 'not_found':
            return jsonify({'error': 'Job not found'}), 404
        
        return jsonify(job_info)
    
    @app.route('/uploads/<path:filename>')
    def download_file(filename):
        """Serve uploaded files."""
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
    
    @app.errorhandler(404)
    def page_not_found(e):
        """Handle 404 errors."""
        return render_template('error.html', 
                            title="Page Not Found", 
                            message="The requested page could not be found.",
                            details=str(e),
                            connections=app.config.get('CONNECTION_STATUS', {})), 404
                            
    @app.errorhandler(500)
    def server_error(e):
        """Handle 500 errors."""
        return render_template('error.html', 
                            title="Server Error", 
                            message="An internal server error occurred.",
                            details=str(e),
                            connections=app.config.get('CONNECTION_STATUS', {})), 500
    
    return app
